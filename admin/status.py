"""Admin Status Dashboard

Comprehensive admin dashboard providing overview and access to all management tasks
including system health, maintenance operations, and monitoring tools.
"""

from flask import render_template, jsonify, current_app, flash, redirect, url_for
from auth.roles import roles_required
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import pytz
import sqlalchemy as sa

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


@roles_required('admin', 'data_manager')
@login_required
def admin_status():
    """Main admin status dashboard showing all system management areas"""

    # Get thumbnail statistics
    try:
        thumbnail_stats = get_thumbnail_statistics()
    except Exception as e:
        current_app.logger.error(f"Error getting thumbnail stats: {e}")
        thumbnail_stats = {
            'direct_uploads': {'total': 0, 'with_original_thumbnails': 0, 'with_edited_thumbnails': 0, 'missing_thumbnails': 0},
            'encounter_files': {'total': 0, 'with_thumbnails': 0, 'missing_thumbnails': 0},
            'storage': {'estimated_thumbnail_size_mb': 0.0}
        }

    # Get maintenance status
    try:
        maintenance_status = get_maintenance_status()
    except Exception as e:
        current_app.logger.error(f"Error getting maintenance status: {e}")
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
        current_app.logger.error(f"Error getting health status: {e}")
        health_status = {
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'recommendations': ['Check application logs', 'Verify system configuration'],
            'performance_metrics': {}
        }

    # Get general system statistics
    system_stats = get_system_statistics()

    # Get recent activity data
    recent_activity = get_recent_activity()

    # Get sequence diagnostics
    sequence_report = get_sequence_report()

    return render_template(
        'admin/status.html',
        thumbnail_stats=thumbnail_stats,
        maintenance_status=maintenance_status,
        health_status=health_status,
        system_stats=system_stats,
        recent_activity=recent_activity,
        sequence_report=sequence_report,
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
            'recent_activity': get_recent_activity()
        }

        return jsonify({
            'success': True,
            'data': status_data
        })

    except Exception as e:
        current_app.logger.error(f"Error getting admin status: {e}")
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
        current_app.logger.error(f"Error getting system statistics: {e}")
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
    except Exception:
        pass

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
    except Exception:
        pass

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
    except Exception:
        pass

    # Sort by timestamp and limit
    recent_activity.sort(key=lambda x: x.get('timestamp', datetime.min), reverse=True)
    return recent_activity[:limit]


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

            table_fq = f'"{row.table_schema}"."{row.table_name}"'
            col_name = f'"{row.column_name}"'

            max_id = db.execute(
                sa.text(f"SELECT COALESCE(MAX({col_name}), 0) FROM {table_fq}")
            ).scalar_one()

            last_value, is_called = db.execute(
                sa.text(f"SELECT last_value, is_called FROM {seq_name}")
            ).one()

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
