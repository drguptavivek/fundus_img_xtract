"""
S3 Sync Status Dashboard

Admin dashboard for viewing and managing S3 synchronization status.
Shows per-hospital sync counts, recent failures, and provides retry functionality.
"""

import logging
from flask import render_template, jsonify, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, and_, desc

from admin import admin_bp
from auth.roles import roles_required
from models import S3Config, S3SyncStatus, Hospital
from db_transaction_manager import transaction_scope
from utils.s3_sync_status import (
    get_sync_counts_by_hospital,
    get_recent_sync_activity,
    get_failed_syncs,
    get_file_by_sync,
    mark_sync_in_progress,
)
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)


def _get_user_hospitals():
    """Get list of hospital IDs the current user can access."""
    if not current_user or not current_user.is_authenticated:
        return []

    # Admins can see all hospitals
    if "admin" in current_user.get_roles():
        with transaction_scope() as db:
            return [h.id for h in db.execute(select(Hospital).order_by(Hospital.id)).scalars().all()]

    # Non-admins see their lab unit hospitals
    if current_user.lab_units:
        return [lab_unit.id for lab_unit in current_user.lab_units]

    return []


@admin_bp.route("/s3-sync-dashboard")
@login_required
@roles_required("admin", "local_admin")
def s3_sync_dashboard():
    """
    Main S3 sync status dashboard.

    Shows per-hospital sync status overview with counts and recent activity.
    """
    user_hospitals = _get_user_hospitals()

    with transaction_scope() as db:
        if not user_hospitals:
            hospitals_data = []
        else:
            # Get hospitals with their S3 configs
            hospitals = db.execute(
                select(Hospital).where(Hospital.id.in_(user_hospitals)).order_by(Hospital.name)
            ).scalars().all()

            hospitals_data = []
            for hospital in hospitals:
                # Get S3 config for this hospital
                s3_config = db.execute(
                    select(S3Config).where(
                        and_(
                            S3Config.hospital_id == hospital.id,
                            S3Config.is_active == True
                        )
                    ).order_by(S3Config.id.desc())
                ).scalar_one_or_none()

                if s3_config:
                    # Get sync counts
                    counts = get_sync_counts_by_hospital(hospital.id)

                    hospitals_data.append({
                        "id": hospital.id,
                        "name": hospital.name,
                        "s3_config_id": s3_config.id,
                        "s3_config_name": s3_config.name,
                        "s3_provider": s3_config.provider,
                        "bucket_name": s3_config.bucket_name,
                        "counts": counts,
                    })

    return render_template("admin/s3_sync_dashboard.html", hospitals=hospitals_data)


@admin_bp.route("/s3-sync-dashboard/hospital/<int:hospital_id>")
@login_required
@roles_required("admin", "local_admin")
def s3_sync_hospital_detail(hospital_id: int):
    """
    Detailed view for a single hospital's S3 sync status.

    Shows recent sync activity, failures, and provides retry options.
    """
    user_hospitals = _get_user_hospitals()
    if hospital_id not in user_hospitals:
        flash("Access denied", "error")
        return redirect(url_for("admin.s3_sync_dashboard"))

    with transaction_scope() as db:
        hospital = db.execute(
            select(Hospital).where(Hospital.id == hospital_id)
        ).scalar_one_or_none()

        if not hospital:
            flash("Hospital not found", "error")
            return redirect(url_for("admin.s3_sync_dashboard"))

        # Get S3 config
        s3_config = db.execute(
            select(S3Config).where(
                and_(
                    S3Config.hospital_id == hospital_id,
                    S3Config.is_active == True
                )
            ).order_by(S3Config.id.desc())
        ).scalar_one_or_none()

        if not s3_config:
            flash("No S3 configuration found for this hospital", "warning")
            return redirect(url_for("admin.s3_sync_dashboard"))

        # Get sync counts
        counts = get_sync_counts_by_hospital(hospital_id)

        # Get recent activity
        recent_activity = get_recent_sync_activity(s3_config.id, limit=100)

        # Get failed syncs
        failed_syncs = get_failed_syncs(s3_config.id, limit=50)

        # Enrich with file details
        failed_with_details = []
        for sync in failed_syncs:
            file_record = get_file_by_sync(sync, db)
            failed_with_details.append({
                "sync": sync,
                "file": file_record,
                "file_uuid": file_record.uuid if file_record else None,
                "file_name": getattr(file_record, 'filename', None) or getattr(file_record, 'original_filename', None),
            })

    return render_template(
        "admin/s3_sync_hospital_detail.html",
        hospital=hospital,
        s3_config=s3_config,
        counts=counts,
        recent_activity=recent_activity,
        failed_syncs=failed_with_details,
    )


@admin_bp.route("/api/s3-sync-status")
@login_required
@roles_required("admin", "local_admin")
def s3_sync_status_api():
    """
    API endpoint for S3 sync status (used by dashboard JS).

    Query params:
        - hospital_id: Filter by hospital
        - status: Filter by status (pending, success, failed, in_progress)
        - limit: Max records (default 50)
    """
    hospital_id = request.args.get("hospital_id", type=int)
    status_filter = request.args.get("status")
    limit = request.args.get("limit", 50, type=int)

    user_hospitals = _get_user_hospitals()

    with transaction_scope() as db:
        query = select(S3SyncStatus)

        # Filter by hospital
        if hospital_id:
            if hospital_id not in user_hospitals:
                return jsonify({"error": "Access denied"}), 403

            # Get S3 config for hospital
            s3_config = db.execute(
                select(S3Config).where(
                    and_(
                        S3Config.hospital_id == hospital_id,
                        S3Config.is_active == True
                    )
                ).scalar_one_or_none()

            if not s3_config:
                return jsonify({"error": "No S3 config for hospital"}), 404

            query = query.where(S3SyncStatus.s3_config_id == s3_config.id)

        # Filter by status
        if status_filter:
            query = query.where(S3SyncStatus.status == status_filter)

        # Order and limit
        query = query.order_by(desc(S3SyncStatus.updated_at)).limit(limit)

        syncs = db.execute(query).scalars().all()

        result = []
        for sync in syncs:
            result.append({
                "id": sync.id,
                "file_type": sync.file_type,
                "file_id": sync.file_id,
                "variant": sync.variant,
                "status": sync.status,
                "attempt_count": sync.attempt_count,
                "last_error": sync.last_error,
                "last_attempt_at": sync.last_attempt_at.isoformat() if sync.last_attempt_at else None,
                "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
                "created_at": sync.created_at.isoformat() if sync.created_at else None,
            })

        return jsonify({
            "syncs": result,
            "count": len(result),
        })


@admin_bp.route("/api/s3-sync-retry/<int:sync_id>", methods=["POST"])
@login_required
@roles_required("admin", "local_admin")
def s3_sync_retry(sync_id: int):
    """
    Retry a failed S3 sync.

    Marks the sync as in_progress so it can be picked up by a background worker.
    """
    with transaction_scope() as db:
        sync = db.execute(
            select(S3SyncStatus).where(S3SyncStatus.id == sync_id)
        ).scalar_one_or_none()

        if not sync:
            return jsonify({"success": False, "message": "Sync record not found"}), 404

        # Check hospital access
        s3_config = db.execute(
            select(S3Config).where(S3Config.id == sync.s3_config_id)
        ).scalar_one_or_none()

        if not s3_config:
            return jsonify({"success": False, "message": "S3 config not found"}), 404

        user_hospitals = _get_user_hospitals()
        if s3_config.hospital_id not in user_hospitals:
            return jsonify({"success": False, "message": "Access denied"}), 403

        # Only failed syncs can be retried
        if sync.status != "failed":
            return jsonify({
                "success": False,
                "message": f"Only failed syncs can be retried (current: {sync.status})"
            }), 400

        # Mark as in_progress
        mark_sync_in_progress(sync_id)

        logger.info(
            "S3 sync retry requested for sync_id=%d (file_type=%s, file_id=%s, variant=%s) by user=%s",
            sync_id, sync.file_type, sync.file_id, sync.variant, current_user.username
        )

        return jsonify({
            "success": True,
            "message": "Sync marked for retry",
            "sync_id": sync_id,
        })


@admin_bp.route("/api/s3-sync-stats")
@login_required
@roles_required("admin", "local_admin")
def s3_sync_stats_api():
    """
    API endpoint for S3 sync statistics (used by dashboard).

    Returns aggregate stats for all accessible hospitals.
    """
    user_hospitals = _get_user_hospitals()

    stats = []
    with transaction_scope() as db:
        for hospital_id in user_hospitals:
            counts = get_sync_counts_by_hospital(hospital_id)
            hospital = db.execute(
                select(Hospital).where(Hospital.id == hospital_id)
            ).scalar_one_or_none()

            if hospital:
                stats.append({
                    "hospital_id": hospital_id,
                    "hospital_name": hospital.name,
                    **counts,
                })

    return jsonify({"stats": stats})
