"""Admin Status Dashboard

Comprehensive admin dashboard providing overview and access to all management tasks
including system health, maintenance operations, and monitoring tools.
"""

from collections import Counter

from flask import render_template, jsonify, current_app, flash, redirect, url_for
from auth.roles import roles_required
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import pytz
import sqlalchemy as sa

from celery_beat_app import celery_app as celery_beat_app
from utils.thumbnail_maintenance_scheduler import (
    get_maintenance_status
)
from admin.thumbnail_management import (
    get_thumbnail_statistics,
    get_system_health,
    api_thumbnail_stats,
    api_maintenance_status
)
from utils.env_loader import get_env
from db_transaction_manager import transaction_scope
from models import CeleryBeatSchedule, Grade, GradingTask, Consensus, DiseaseGrading, User, LabUnit, LinkedDiseaseGrading
from utils.celery_queue_config import infer_celery_queue
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.log_sanitize import sanitize_log_value


@roles_required('admin', 'data_manager')
@login_required
def admin_status():
    """Main admin status dashboard showing all system management areas"""

    # Get thumbnail statistics
    try:
        thumbnail_stats = get_thumbnail_statistics()
    except Exception as e:
        current_app.logger.error(
            "Error getting thumbnail stats: %s",
            sanitize_log_value(e),
        )
        thumbnail_stats = {
            'direct_uploads': {'total': 0, 'with_original_thumbnails': 0, 'with_edited_thumbnails': 0, 'missing_thumbnails': 0},
            'encounter_files': {'total': 0, 'with_thumbnails': 0, 'missing_thumbnails': 0},
            'storage': {'estimated_thumbnail_size_mb': 0.0}
        }

    # Get maintenance status
    try:
        maintenance_status = get_maintenance_status()
    except Exception as e:
        current_app.logger.error(
            "Error getting maintenance status: %s",
            sanitize_log_value(e),
        )
        maintenance_status = {
            'currently_running': False,
            'last_run': None,
            'scheduled_next': None,
            'tasks': []
        }

    # Get system health
    try:
        health_status = get_system_health()
    except Exception as e:
        current_app.logger.error(
            "Error getting health status: %s",
            sanitize_log_value(e),
        )
        health_status = {
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'recommendations': ['Check application logs', 'Verify system configuration'],
            'performance_metrics': {}
        }

    # Get general system statistics
    system_stats = get_system_statistics()

    # Grading inconsistencies (Resident2 present, Resident missing)
    try:
        with transaction_scope() as db:
            resident2_exists = (
                db.query(Grade.task_id)
                .filter(sa.and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident2"))
            )
            resident_missing = ~sa.exists().where(
                sa.and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident")
            )
            grading_inconsistency_count = (
                db.query(GradingTask.id)
                .filter(resident_missing)
                .filter(resident2_exists.exists())
                .count()
            )
    except Exception as e:
        current_app.logger.error(
            "Error computing grading inconsistencies: %s",
            sanitize_log_value(e),
        )
        grading_inconsistency_count = 0

    # Review vs consensus inconsistencies (review grade differs/missing consensus)
    try:
        with transaction_scope() as db:
            review_consensus_mismatch_count = _get_review_consensus_mismatch_count(db)
    except Exception as e:
        current_app.logger.error(
            "Error computing review/consensus inconsistencies: %s",
            sanitize_log_value(e),
        )
        review_consensus_mismatch_count = 0

    # Linked task state inconsistencies (primary vs linked mismatch)
    try:
        with transaction_scope() as db:
            PrimaryTask = sa.orm.aliased(GradingTask)
            LinkedTask = sa.orm.aliased(GradingTask)
            image_match = sa.or_(
                sa.and_(
                    PrimaryTask.encounter_file_id.isnot(None),
                    PrimaryTask.encounter_file_id == LinkedTask.encounter_file_id,
                ),
                sa.and_(
                    PrimaryTask.direct_image_upload_id.isnot(None),
                    PrimaryTask.direct_image_upload_id == LinkedTask.direct_image_upload_id,
                ),
                sa.and_(
                    PrimaryTask.patient_encounter_id.isnot(None),
                    PrimaryTask.patient_encounter_id == LinkedTask.patient_encounter_id,
                ),
            )
            mismatch_filter = sa.or_(
                sa.and_(PrimaryTask.state == "resident_done", LinkedTask.state == "pending"),
                sa.and_(
                    PrimaryTask.state.in_(["resident2_done", "final"]),
                    LinkedTask.state == "resident_done",
                ),
            )
            linked_task_inconsistency_count = (
                db.query(PrimaryTask.id)
                .join(LinkedTask, image_match)
                .join(
                    LinkedDiseaseGrading,
                    sa.and_(
                        LinkedDiseaseGrading.primary_disease_id == PrimaryTask.disease_id,
                        LinkedDiseaseGrading.linked_disease_id == LinkedTask.disease_id,
                        LinkedDiseaseGrading.is_active.is_(True),
                    ),
                )
                .filter(mismatch_filter)
                .count()
            )
    except Exception as e:
        current_app.logger.error(
            "Error computing linked task inconsistencies: %s",
            sanitize_log_value(e),
        )
        linked_task_inconsistency_count = 0

    # Get recent activity data
    recent_activity = get_recent_activity()

    # Get sequence diagnostics
    sequence_report = get_sequence_report()

    celery_status = get_celery_task_status()

    # Scoped users for filters (based on current user's lab units)
    scoped_users = []
    try:
        with transaction_scope() as db:
            lab_unit_ids = list(get_user_lab_unit_ids_no_admin_override(current_user.id))
            if lab_unit_ids:
                scoped_users = [
                    {"id": user.id, "username": user.username}
                    for user in (
                        db.query(User)
                        .join(User.lab_units)
                        .filter(LabUnit.id.in_(lab_unit_ids))
                        .distinct()
                        .order_by(User.username.asc())
                        .all()
                    )
                ]
    except Exception as e:
        current_app.logger.error(
            "Error loading scoped users: %s",
            sanitize_log_value(e),
        )

    return render_template(
        'admin/status.html',
        thumbnail_stats=thumbnail_stats,
        maintenance_status=maintenance_status,
        health_status=health_status,
        system_stats=system_stats,
        recent_activity=recent_activity,
        sequence_report=sequence_report,
        celery_status=celery_status,
        scoped_users=scoped_users,
        grading_inconsistency_count=grading_inconsistency_count,
        linked_task_inconsistency_count=linked_task_inconsistency_count,
        review_consensus_mismatch_count=review_consensus_mismatch_count,
        current_time=datetime.now(pytz.UTC)
    )


@roles_required('admin', 'data_manager')
def api_admin_status():
    """API endpoint for getting comprehensive admin status data"""

    try:
        # Collect all status data
        status_data = {
            'timestamp': datetime.now(pytz.UTC).isoformat(),
            'thumbnail': get_thumbnail_statistics(),
            'maintenance': get_maintenance_status(),
            'health': get_system_health(),
            'system': get_system_statistics(),
            'recent_activity': get_recent_activity(),
            'celery': get_celery_task_status(),
        }

        return jsonify({
            'success': True,
            'data': status_data
        })

    except Exception as e:
        current_app.logger.error(
            "Error getting admin status: %s",
            sanitize_log_value(e),
        )
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now(pytz.UTC).isoformat()
        }), 500


@roles_required('admin')
def refresh_sequences():
    """Admin action to realign all sequences to current table maxima."""
    try:
        from db_transaction_manager import transaction_scope

        with transaction_scope() as db:
            _ensure_refresh_function(db)
            db.execute(sa.text("SELECT refresh_all_sequences();"))
            db.commit()
        flash("Sequences refreshed to match table maxima.", "success")
    except Exception as exc:
        current_app.logger.exception("Failed to refresh sequences")
        flash(f"Failed to refresh sequences: {exc}", "danger")
    return redirect(url_for("admin.admin_status"))


@roles_required('admin', 'data_manager')
def api_sequences_status():
    """API to get current sequence vs max diagnostics."""
    try:
        report = get_sequence_report()
        return jsonify({"success": True, "data": report})
    except Exception as exc:
        current_app.logger.exception("Failed to get sequence diagnostics")
    return jsonify({"success": False, "error": str(exc)}), 500


@roles_required('admin', 'data_manager')
def api_celery_task_status():
    """API endpoint for Celery schedule/task monitoring on admin status page."""
    try:
        return jsonify({
            "success": True,
            "data": get_celery_task_status(),
        })
    except Exception as exc:
        current_app.logger.exception("Failed to get celery task status")
        return jsonify({
            "success": False,
            "error": str(exc),
            "timestamp": datetime.now(pytz.UTC).isoformat(),
        }), 500


def get_system_statistics():
    """Get general system statistics for admin dashboard"""

    try:
        from db_transaction_manager import transaction_scope
        from models import DirectImageUpload, EncounterFile, ZipFile, Job, JobItem, User

        with transaction_scope() as db:
            # User statistics
            total_users = db.query(User).count()

            # Image statistics
            total_direct_uploads = db.query(DirectImageUpload).count()
            total_encounter_files = db.query(EncounterFile).count()

            # Job statistics
            total_jobs = db.query(Job).count()
            total_job_items = db.query(JobItem).count()

            # Recent activity (last 7 days)
            week_ago = datetime.now(pytz.UTC) - timedelta(days=7)
            recent_jobs = db.query(Job).filter(Job.created_at >= week_ago).count()

            # ZIP file statistics
            total_zips = db.query(ZipFile).count()
            recent_zips = db.query(ZipFile).filter(ZipFile.upload_date >= week_ago).count()

            return {
                'users': {
                    'total': total_users,
                    'active': recent_jobs  # Proxy for active users
                },
                'images': {
                    'direct_uploads': total_direct_uploads,
                    'encounter_files': total_encounter_files,
                    'total': total_direct_uploads + total_encounter_files
                },
                'jobs': {
                    'total': total_jobs,
                    'total_items': total_job_items,
                    'recent_week': recent_jobs
                },
                'storage': {
                    'total_zips': total_zips,
                    'recent_zips': recent_zips,
                    'zip_size_estimate': total_zips * 2  # Approximate MB
                }
            }

    except Exception as e:
        current_app.logger.error(
            "Error getting system statistics: %s",
            sanitize_log_value(e),
        )
        return {
            'users': {'total': 0, 'active': 0},
            'images': {'direct_uploads': 0, 'encounter_files': 0, 'total': 0},
            'jobs': {'total': 0, 'total_items': 0, 'recent_week': 0},
            'storage': {'total_zips': 0, 'recent_zips': 0, 'zip_size_estimate': 0}
        }


def get_recent_activity(limit=10):
    """Get recent system activity for dashboard"""

    recent_activity = []

    # Recent maintenance activities
    try:
        maintenance_status = get_maintenance_status()
        if maintenance_status.get('last_run'):
            recent_activity.append({
                'type': 'maintenance',
                'title': 'Last Maintenance',
                'description': maintenance_status['last_run'].get('operation', 'Unknown'),
                'timestamp': maintenance_status['last_run'].get('completed_at'),
                'status': maintenance_status['last_run'].get('status', 'unknown')
            })
    except Exception as e:
        current_app.logger.warning("Failed to fetch recent maintenance activity: %s", sanitize_log_value(e))

    # Recent thumbnail statistics changes
    try:
        stats = get_thumbnail_statistics()
        total_images = (
            stats.get('direct_uploads', {}).get('total', 0) +
            stats.get('encounter_files', {}).get('total', 0)
        )
        missing_thumbnails = (
            stats.get('direct_uploads', {}).get('missing_thumbnails', 0) +
            stats.get('encounter_files', {}).get('missing_thumbnails', 0)
        )

        if total_images > 0 and missing_thumbnails > 0:
            missing_percentage = (missing_thumbnails / total_images) * 100
            recent_activity.append({
                'type': 'thumbnail',
                'title': 'Thumbnail Coverage',
                'description': f'{total_images - missing_thumbnails}/{total_images} images have thumbnails',
                'timestamp': datetime.now(pytz.UTC),
                'status': 'warning' if missing_percentage > 10 else 'info',
                'percentage': f'{100 - missing_percentage:.1f}%'
            })
    except Exception as e:
        current_app.logger.warning("Failed to fetch recent thumbnail activity: %s", sanitize_log_value(e))

    # Health status changes
    try:
        health = get_system_health()
        if health.get('status') != 'healthy':
            recent_activity.append({
                'type': 'health',
                'title': 'System Health',
                'description': f"Status: {health.get('status', 'unknown')}",
                'timestamp': datetime.now(pytz.UTC),
                'status': health.get('status', 'unknown'),
                'issues_count': len(health.get('issues', []))
            })
    except Exception as e:
        current_app.logger.warning("Failed to fetch recent health activity: %s", sanitize_log_value(e))

    # Sort by timestamp and limit
    recent_activity.sort(key=lambda x: x.get('timestamp', datetime.min), reverse=True)
    return recent_activity[:limit]


def _serialize_schedule_expression(row: CeleryBeatSchedule) -> str:
    schedule_type = row["schedule_type"] if isinstance(row, dict) else row.schedule_type
    interval_seconds = row["interval_seconds"] if isinstance(row, dict) else row.interval_seconds
    crontab_minute = row["crontab_minute"] if isinstance(row, dict) else row.crontab_minute
    crontab_hour = row["crontab_hour"] if isinstance(row, dict) else row.crontab_hour
    crontab_day_of_month = row["crontab_day_of_month"] if isinstance(row, dict) else row.crontab_day_of_month
    crontab_month_of_year = row["crontab_month_of_year"] if isinstance(row, dict) else row.crontab_month_of_year
    crontab_day_of_week = row["crontab_day_of_week"] if isinstance(row, dict) else row.crontab_day_of_week

    if schedule_type == "interval":
        if interval_seconds:
            return f"every {interval_seconds}s"
        return "interval"
    return " ".join([
        crontab_minute or "*",
        crontab_hour or "*",
        crontab_day_of_month or "*",
        crontab_month_of_year or "*",
        crontab_day_of_week or "*",
    ])


def _serialize_code_schedule_expression(entry: dict) -> str:
    schedule_obj = entry.get("schedule")
    if schedule_obj is None:
        return "unknown"
    run_every = getattr(schedule_obj, "run_every", None)
    if run_every is not None:
        seconds = int(run_every.total_seconds())
        return f"every {seconds}s"
    minute = getattr(schedule_obj, "_orig_minute", None)
    hour = getattr(schedule_obj, "_orig_hour", None)
    day_of_month = getattr(schedule_obj, "_orig_day_of_month", None)
    month_of_year = getattr(schedule_obj, "_orig_month_of_year", None)
    day_of_week = getattr(schedule_obj, "_orig_day_of_week", None)
    if any(value is not None for value in [minute, hour, day_of_month, month_of_year, day_of_week]):
        return " ".join([
            str(minute or "*"),
            str(hour or "*"),
            str(day_of_month or "*"),
            str(month_of_year or "*"),
            str(day_of_week or "*"),
        ])
    return str(schedule_obj)


def _build_celery_task_status_payload(db_rows, code_entries, now: datetime) -> dict:
    def _value(row, key):
        return row[key] if isinstance(row, dict) else getattr(row, key)

    task_counts = Counter()
    rows: list[dict] = []

    for row in db_rows:
        task_counts[_value(row, "task_name")] += 1
    for _, entry in code_entries.items():
        task_name = entry.get("task")
        if task_name:
            task_counts[task_name] += 1

    for row in db_rows:
        task_name = _value(row, "task_name")
        inferred_queue = _value(row, "queue") or infer_celery_queue(task_name)
        issues: list[str] = []
        if not inferred_queue:
            issues.append("No queue configured or inferred")
        if task_counts[task_name] > 1:
            issues.append(f"Duplicate schedule definition ({task_counts[task_name]} total)")
        if _value(row, "enabled") and _value(row, "last_run_at") is None and _value(row, "next_run_at") is None:
            issues.append("No persisted run telemetry")

        if not _value(row, "enabled"):
            status = "disabled"
        elif issues:
            status = "warning"
        else:
            status = "healthy"

        rows.append({
            "name": _value(row, "name"),
            "task_name": task_name,
            "source": "db",
            "queue": inferred_queue,
            "queue_explicit": bool(_value(row, "queue")),
            "enabled": _value(row, "enabled"),
            "schedule_type": _value(row, "schedule_type"),
            "schedule": _serialize_schedule_expression(row),
            "last_run_at": _value(row, "last_run_at").isoformat() if _value(row, "last_run_at") else None,
            "next_run_at": _value(row, "next_run_at").isoformat() if _value(row, "next_run_at") else None,
            "status": status,
            "issues": issues,
        })

    for name, entry in sorted(code_entries.items()):
        task_name = entry.get("task")
        options = entry.get("options") or {}
        queue_name = options.get("queue") or infer_celery_queue(task_name or "")
        issues: list[str] = []
        if task_counts[task_name] > 1:
            issues.append(f"Duplicate schedule definition ({task_counts[task_name]} total)")

        rows.append({
            "name": name,
            "task_name": task_name,
            "source": "code",
            "queue": queue_name,
            "queue_explicit": "queue" in options,
            "enabled": True,
            "schedule_type": "code",
            "schedule": _serialize_code_schedule_expression(entry),
            "last_run_at": None,
            "next_run_at": None,
            "status": "warning" if issues else "healthy",
            "issues": issues,
        })

    rows.sort(key=lambda item: (item["status"] != "warning", item["source"], item["name"]))

    warning_count = sum(1 for row in rows if row["status"] == "warning")
    disabled_count = sum(1 for row in rows if row["status"] == "disabled")

    return {
        "timestamp": now.isoformat(),
        "summary": {
            "total": len(rows),
            "db_entries": len(db_rows),
            "code_entries": len(code_entries),
            "warning_count": warning_count,
            "disabled_count": disabled_count,
        },
        "rows": rows,
    }


def get_celery_task_status() -> dict:
    """Collect Celery schedule/task status for the admin dashboard."""
    now = datetime.now(pytz.UTC)
    code_entries = dict(celery_beat_app.conf.beat_schedule or {})
    with transaction_scope() as db:
        db_rows = [
            {
                "name": row.name,
                "task_name": row.task_name,
                "queue": row.queue,
                "enabled": row.enabled,
                "schedule_type": row.schedule_type,
                "interval_seconds": row.interval_seconds,
                "crontab_minute": row.crontab_minute,
                "crontab_hour": row.crontab_hour,
                "crontab_day_of_week": row.crontab_day_of_week,
                "crontab_day_of_month": row.crontab_day_of_month,
                "crontab_month_of_year": row.crontab_month_of_year,
                "last_run_at": row.last_run_at,
                "next_run_at": row.next_run_at,
            }
            for row in (
            db.query(CeleryBeatSchedule)
            .order_by(CeleryBeatSchedule.enabled.desc(), CeleryBeatSchedule.name.asc())
            .all()
            )
        ]
    return _build_celery_task_status_payload(db_rows, code_entries, now)


def get_management_tools_status():
    """Get status of various management tools and systems"""

    tools_status = {}

    # Thumbnail system
    try:
        from utils.image_processing import test_thumbnail_generation
        thumbnail_test = test_thumbnail_generation()
        tools_status['thumbnail_generation'] = {
            'status': 'healthy' if thumbnail_test else 'error',
            'message': 'Thumbnail generation working' if thumbnail_test else 'Thumbnail generation failed'
        }
    except Exception as e:
        tools_status['thumbnail_generation'] = {
            'status': 'error',
            'message': f'Thumbnail generation test failed: {str(e)}'
        }

    # Database connectivity
    try:
        from db_transaction_manager import transaction_scope
        with transaction_scope() as db:
            db.execute("SELECT 1").fetchone()
        tools_status['database'] = {
            'status': 'healthy',
            'message': 'Database connection working'
        }
    except Exception as e:
        tools_status['database'] = {
            'status': 'error',
            'message': f'Database connection failed: {str(e)}'
        }

def _get_review_consensus_mismatch_count(db) -> int:
    """Count tasks where latest review grade differs from consensus (or consensus missing)."""
    latest_review = (
        db.query(
            Grade.task_id.label("task_id"),
            Grade.disease_grading_id.label("review_grading_id"),
            sa.func.row_number()
            .over(
                partition_by=Grade.task_id,
                order_by=[Grade.updated_at.desc().nullslast(), Grade.id.desc()],
            )
            .label("rn"),
        )
        .filter(Grade.role_slot == "review")
        .subquery()
    )

    q = (
        db.query(sa.func.count())
        .select_from(GradingTask)
        .join(latest_review, latest_review.c.task_id == GradingTask.id)
        .outerjoin(Consensus, Consensus.task_id == GradingTask.id)
        .outerjoin(DiseaseGrading, DiseaseGrading.id == Consensus.final_disease_grading_id)
        .filter(latest_review.c.rn == 1)
        .filter(
            sa.or_(
                Consensus.final_disease_grading_id.is_(None),
                Consensus.final_disease_grading_id != latest_review.c.review_grading_id,
            )
        )
    )
    return q.scalar() or 0

    # File system access
    try:
        from models import UPLOAD_DIR, IMAGE_DIR
        upload_accessible = UPLOAD_DIR.exists() and UPLOAD_DIR.is_dir()
        image_accessible = IMAGE_DIR.exists() and IMAGE_DIR.is_dir()
        tools_status['file_system'] = {
            'status': 'healthy' if upload_accessible and image_accessible else 'warning',
            'message': f'Upload dir: {"OK" if upload_accessible else "ERROR"}, Image dir: {"OK" if image_accessible else "ERROR"}'
        }
    except Exception as e:
        tools_status['file_system'] = {
            'status': 'error',
            'message': f'File system check failed: {str(e)}'
        }

    return tools_status


def get_sequence_report():
    """Collect sequence vs table max diagnostics."""
    from db_transaction_manager import transaction_scope

    report = {
        "checked_at": datetime.now(pytz.UTC),
        "mismatches": [],
        "total_sequences": 0,
        "entries": [],
    }

    with transaction_scope() as db:
        sequences = db.execute(sa.text("""
            SELECT
                table_schema,
                table_name,
                column_name,
                pg_get_serial_sequence(format('%I.%I', table_schema, table_name), column_name) AS seq_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND pg_get_serial_sequence(format('%I.%I', table_schema, table_name), column_name) IS NOT NULL
        """)).all()

        report["total_sequences"] = len(sequences)

        for row in sequences:
            seq_name = row.seq_name
            if not seq_name:
                continue

            # Use SQLAlchemy expression language to prevent SQL injection
            t = sa.table(row.table_name, schema=row.table_schema)
            c = sa.column(row.column_name)
            stmt = sa.select(sa.func.coalesce(sa.func.max(c), 0)).select_from(t)
            max_id = db.execute(stmt).scalar_one()

            # Handle sequence name (might be 'schema.rel' or just 'rel')
            # pg_get_serial_sequence usually returns 'schema.sequence' or 'sequence'
            seq_parts = seq_name.split('.')
            if len(seq_parts) == 2:
                seq_t = sa.table(seq_parts[1], schema=seq_parts[0])
            else:
                seq_t = sa.table(seq_name)
            
            stmt_seq = sa.select(sa.column("last_value"), sa.column("is_called")).select_from(seq_t)
            last_value, is_called = db.execute(stmt_seq).one()

            next_value = last_value + 1 if is_called else last_value
            mismatch = max_id >= next_value

            entry = {
                "table": f"{row.table_schema}.{row.table_name}",
                "column": row.column_name,
                "sequence": seq_name,
                "max_id": int(max_id) if max_id is not None else 0,
                "last_value": int(last_value),
                "is_called": bool(is_called),
                "next_value": int(next_value),
                "mismatch": mismatch,
            }
            report["entries"].append(entry)

            if mismatch:
                report["mismatches"].append(entry)

    return report


def _ensure_refresh_function(db):
    """Ensure refresh_all_sequences function exists before invoking."""
    db.execute(sa.text("""
        CREATE OR REPLACE FUNCTION refresh_all_sequences()
        RETURNS void AS $$
        DECLARE
            rec record;
            max_id bigint;
            set_to bigint;
            is_called boolean;
        BEGIN
            FOR rec IN
                SELECT
                    format('%I.%I', table_schema, table_name) AS fqtn,
                    column_name,
                    pg_get_serial_sequence(format('%I.%I', table_schema, table_name), column_name) AS seq_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND pg_get_serial_sequence(format('%I.%I', table_schema, table_name), column_name) IS NOT NULL
            LOOP
                EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %s', rec.column_name, rec.fqtn) INTO max_id;
                set_to := GREATEST(max_id, 1);
                is_called := max_id > 0;
                EXECUTE format('SELECT setval(%L, %s, %L)', rec.seq_name, set_to, is_called);
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """))


def register_status_routes(bp):
    """Register admin status routes with the blueprint"""

    bp.add_url_rule(
        '/status',
        view_func=admin_status,
        methods=['GET']
    )

    bp.add_url_rule(
        '/api/admin/status',
        view_func=api_admin_status,
        methods=['GET']
    )

    bp.add_url_rule(
        '/api/celery/tasks/status',
        view_func=api_celery_task_status,
        methods=['GET']
    )
