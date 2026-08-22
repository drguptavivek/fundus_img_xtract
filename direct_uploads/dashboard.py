# direct_uploads/dashboard.py

import logging
from flask import request, render_template, redirect, url_for, flash, current_app, session
from flask_login import current_user
from sqlalchemy import select, func, and_, or_
from datetime import datetime, timedelta, timezone
from pathlib import Path
from models import (
    User,
    LabUnit,
    Hospital,
    DirectImageUpload,
    DirectImageVerify,
    Camera,
    Disease,
    Area,
    Grade,
    GradingTask,
    DiseaseGrading,
)
from auth.utils import utcnow

from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from authz import scope
from utils.rate_limiter import rate_limit
from utils.fileUtils import abs_from_parts
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.thumbnail_cleanup import add_thumbnail_cleanup_to_direct_upload_deletion
from utils.log_sanitize import sanitize_log_value


editing_logger = logging.getLogger("editing")



# --- helpers ---
def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_text(value: object) -> str:
    """Convert a value into a safe string for logging."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _log_image_attribute_changes(upload: DirectImageUpload, changes: list[dict[str, object]]) -> None:
    """Append attribute change details to the direct image edit log."""
    if not changes:
        return

    log_location = current_app.config.get("DIRECT_IMAGE_EDIT_LOG", "logs/direct_image_edit.log")
    log_path = Path(log_location)
    if not log_path.is_absolute():
        log_path = Path(current_app.root_path) / log_path

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        editing_logger.error(
            "Unable to create directory for direct image edit log at %s: %s",
            log_path.parent,
            exc,
        )
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    user_identifier = (
        f"{current_user.id}:{current_user.username}"
        if current_user.is_authenticated
        else "anonymous"
    )

    lines: list[str] = []
    for change in changes:
        field_name = _safe_text(change.get("field"))
        old_value = _safe_text(change.get("old"))
        new_value = _safe_text(change.get("new"))
        lines.append(
            "\t".join(
                [
                    timestamp,
                    f"user={user_identifier}",
                    f"upload_id={upload.id}",
                    f"filename={upload.filename}",
                    f"field={field_name}",
                    f"old={old_value}",
                    f"new={new_value}",
                ]
            )
            + "\n"
        )

    try:
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.writelines(lines)
    except OSError as exc:
        editing_logger.error(
            "Failed to write to direct image edit log at %s: %s",
            log_path,
            exc,
        )

@bp.route("/direct/dashboard", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
@rate_limit("10000 per hour, 500 per minute", methods=["GET"])  # More permissive for pagination/browsing
@rate_limit("3000 per hour, 60 per minute", methods=["POST"])   # More restrictive for operations
def dashboard():
    with get_db_session() as db_session:
        # Site admins and master admins can access dashboard if they have a hospital assignment
        # Regular users need explicit lab unit assignments
        can_manage_others = current_user.has_role(
            "admin", "data_manager", "local_admin", "fileUploader", "optometrist"
        )
        
        # Check access: Master admin always allowed, Site admin needs hospital_id, others need lab units
        if current_user.has_role("local_admin"):
            # Site admin needs hospital assignment
            if not current_user.hospital_id:
                flash("You do not have a hospital assignment.", "warning")
                if request.method == "POST":
                    return redirect(url_for("direct_uploads.dashboard"), code=303)
                return redirect(url_for("home.index"))
        else:
            # Regular users need lab unit assignments
            allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
            if not allowed_lab_unit_ids:
                flash("You do not have access to any lab units.", "warning")
                if request.method == "POST":
                    return redirect(url_for("direct_uploads.dashboard"), code=303)
                return redirect(url_for("home.index"))
        
        # Get lab units for filter dropdowns (still needed for UI)
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        allowed_lab_unit_ids_list = list(allowed_lab_unit_ids)
        
        allowed_hospital_ids: set[int] = set()
        if allowed_lab_unit_ids_list:
            allowed_hospital_ids = {
                hid for hid, in db_session.execute(
                    select(LabUnit.hospital_id).where(LabUnit.id.in_(allowed_lab_unit_ids_list))
                )
                if hid is not None
            }

        if request.method == "POST":
            selected_ids = request.form.getlist('selected_uploads')
            action = request.form.get('action')

            if len(selected_ids) > 50:
                flash("Maximum 50 files can be processed in a single operation.", "danger")
                return redirect(url_for("direct_uploads.dashboard"), code=303)

            elif action == "bulk_edit" and selected_ids:
                # Get the new values from the form
                new_hospital_id = request.form.get('new_hospital_id')
                new_lab_unit_id = request.form.get('new_lab_unit_id')
                new_camera_id = request.form.get('new_camera_id')
                new_disease_id = request.form.get('new_disease_id')
                new_area_id = request.form.get('new_area_id')
                new_is_mydriatic = request.form.get('new_is_mydriatic')

                # Coerce IDs safely
                try:
                    ids = [int(x) for x in selected_ids]
                except Exception:
                    ids = [int(x) for x in selected_ids if str(x).isdigit()]

                if not ids:
                    flash("No valid rows selected.", "warning")
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                q = select(DirectImageUpload).where(DirectImageUpload.id.in_(ids))
                q = scope(db_session, q, DirectImageUpload, current_user, 'upload.direct.view')

                if not can_manage_others:
                    q = q.where(DirectImageUpload.uploader_id == current_user.id)
                    
                rows = db_session.execute(q).scalars().all()

                if not rows:
                    flash("No uploads matched your selection and permissions.", "warning")
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                if new_lab_unit_id:
                    try:
                        new_lab_unit_id_int = int(new_lab_unit_id)
                    except (TypeError, ValueError):
                        flash("Invalid lab unit selection.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)
                    
                    # Validate new lab unit - check if it's within user's scope
                    lu_check = db_session.execute(
                        scope(db_session, select(LabUnit).where(LabUnit.id == new_lab_unit_id_int), LabUnit, current_user, 'upload.direct.view')
                    ).scalar_one_or_none()
                    if not lu_check:
                        flash("You cannot assign uploads to that lab unit.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)

                if new_hospital_id:
                    try:
                        new_hospital_id_int = int(new_hospital_id)
                    except (TypeError, ValueError):
                        flash("Invalid hospital selection.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)
                    
                    # Validate hospital - check if user has access to this hospital
                    if current_user.has_role("local_admin") and new_hospital_id_int != current_user.hospital_id:
                        flash("You cannot assign uploads to that hospital.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)

                upload_ids = [upload.id for upload in rows]
                tasks_by_upload: dict[int, list[GradingTask]] = {}
                if upload_ids:
                    task_rows = db_session.execute(
                        select(GradingTask).where(GradingTask.direct_image_upload_id.in_(upload_ids))
                    ).scalars().all()
                    for task in task_rows:
                        if task.direct_image_upload_id is None:
                            continue
                        tasks_by_upload.setdefault(task.direct_image_upload_id, []).append(task)

                blocked_uploads: list[tuple[DirectImageUpload, list[GradingTask]]] = []
                updatable_uploads: list[tuple[DirectImageUpload, list[GradingTask]]] = []
                for upload in rows:
                    related_tasks = tasks_by_upload.get(upload.id, [])
                    if any(task.state != 'pending' for task in related_tasks):
                        blocked_uploads.append((upload, related_tasks))
                        continue
                    updatable_uploads.append((upload, related_tasks))

                if not updatable_uploads:
                    skipped_payload = [
                        {
                            "upload_id": upload.id,
                            "filename": upload.filename,
                            "non_pending_states": sorted(
                                {task.state for task in related_tasks if task.state != 'pending'}
                            ),
                        }
                        for upload, related_tasks in blocked_uploads
                    ]
                    editing_logger.warning(
                        "Bulk edit aborted; uploads blocked=%s user_id=%s",
                        [item["upload_id"] for item in skipped_payload],
                        current_user.id,
                    )
                    session['bulk_edit_result'] = {
                        "updated": [],
                        "skipped": skipped_payload,
                        "updated_task_count": 0,
                    }
                    db_session.rollback()
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                new_hospital_id_int = int(new_hospital_id) if new_hospital_id else None
                new_lab_unit_id_int = int(new_lab_unit_id) if new_lab_unit_id else None
                new_camera_id_int = int(new_camera_id) if new_camera_id else None
                new_disease_id_int = int(new_disease_id) if new_disease_id else None
                new_area_id_int = int(new_area_id) if new_area_id else None
                new_is_mydriatic_bool = (
                    new_is_mydriatic == 'on' if new_is_mydriatic is not None else None
                )

                def _resolve_name(model_cls, entity_id: int | None) -> str | None:
                    if entity_id is None:
                        return None
                    entity = db_session.get(model_cls, entity_id)
                    return getattr(entity, "name", str(entity_id)) if entity is not None else str(entity_id)

                new_value_names = {
                    "hospital_id": _resolve_name(Hospital, new_hospital_id_int),
                    "lab_unit_id": _resolve_name(LabUnit, new_lab_unit_id_int),
                    "camera_id": _resolve_name(Camera, new_camera_id_int),
                    "disease_id": _resolve_name(Disease, new_disease_id_int),
                    "area_id": _resolve_name(Area, new_area_id_int),
                }

                updated_count = 0
                updated_tasks = 0
                updated_payload: list[dict[str, object]] = []
                for upload, related_tasks in updatable_uploads:
                    changed_task_ids: list[int] = []
                    field_changes: list[dict[str, str | bool | None]] = []
                    if new_hospital_id_int is not None:
                        old_id = upload.hospital_id
                        if old_id != new_hospital_id_int:
                            old_name = getattr(upload.hospital, "name", str(old_id))
                            field_changes.append(
                                {
                                    "field": "Hospital",
                                    "old": old_name,
                                    "new": new_value_names["hospital_id"],
                                }
                            )
                        upload.hospital_id = new_hospital_id_int
                    if new_lab_unit_id_int is not None:
                        old_id = upload.lab_unit_id
                        if old_id != new_lab_unit_id_int:
                            old_name = getattr(upload.lab_unit, "name", str(old_id))
                            field_changes.append(
                                {
                                    "field": "Lab Unit",
                                    "old": old_name,
                                    "new": new_value_names["lab_unit_id"],
                                }
                            )
                        upload.lab_unit_id = new_lab_unit_id_int
                    if new_camera_id_int is not None:
                        old_id = upload.camera_id
                        if old_id != new_camera_id_int:
                            old_name = getattr(upload.camera, "name", str(old_id))
                            field_changes.append(
                                {
                                    "field": "Camera",
                                    "old": old_name,
                                    "new": new_value_names["camera_id"],
                                }
                            )
                        upload.camera_id = new_camera_id_int
                    if new_disease_id_int is not None:
                        old_id = upload.disease_id
                        if old_id != new_disease_id_int:
                            old_name = getattr(upload.disease, "name", str(old_id))
                            field_changes.append(
                                {
                                    "field": "Disease",
                                    "old": old_name,
                                    "new": new_value_names["disease_id"],
                                }
                            )
                        upload.disease_id = new_disease_id_int
                    if new_area_id_int is not None:
                        old_id = upload.area_id
                        if old_id != new_area_id_int:
                            old_name = getattr(upload.area, "name", str(old_id))
                            field_changes.append(
                                {
                                    "field": "Area",
                                    "old": old_name,
                                    "new": new_value_names["area_id"],
                                }
                            )
                        upload.area_id = new_area_id_int
                    if new_is_mydriatic_bool is not None:
                        old_bool = upload.is_mydriatic
                        if old_bool != new_is_mydriatic_bool:
                            field_changes.append(
                                {
                                    "field": "Mydriatic",
                                    "old": "Yes" if old_bool else "No",
                                    "new": "Yes" if new_is_mydriatic_bool else "No",
                                }
                            )
                        upload.is_mydriatic = new_is_mydriatic_bool

                    for task in related_tasks:
                        task_changed = False
                        if new_lab_unit_id_int is not None and task.lab_unit_id != new_lab_unit_id_int:
                            task.lab_unit_id = new_lab_unit_id_int
                            task_changed = True
                        if new_disease_id_int is not None and task.disease_id != new_disease_id_int:
                            task.disease_id = new_disease_id_int
                            task_changed = True
                        if task_changed:
                            task.updated_at = utcnow()
                            updated_tasks += 1
                            changed_task_ids.append(task.id)

                    if field_changes:
                        _log_image_attribute_changes(upload, field_changes)

                    updated_count += 1
                    updated_payload.append(
                        {
                            "upload_id": upload.id,
                            "filename": upload.filename,
                            "changes": field_changes,
                            "updated_task_ids": changed_task_ids,
                        }
                    )

                skipped_payload = [
                    {
                        "upload_id": upload.id,
                        "filename": upload.filename,
                        "non_pending_states": sorted(
                            {task.state for task in related_tasks if task.state != 'pending'}
                        ),
                    }
                    for upload, related_tasks in blocked_uploads
                ]

                db_session.commit()
                session['bulk_edit_result'] = {
                    "updated": updated_payload,
                    "skipped": skipped_payload,
                    "updated_task_count": updated_tasks,
                }
                editing_logger.info(
                    "Bulk edit applied to %s uploads; pending tasks updated=%s by user_id=%s",
                    updated_count,
                    updated_tasks,
                    current_user.id,
                )
                if skipped_payload:
                    editing_logger.warning(
                        "Bulk edit skipped uploads=%s user_id=%s",
                        [item["upload_id"] for item in skipped_payload],
                        current_user.id,
                    )
                return redirect(url_for("direct_uploads.dashboard"), code=303)

            elif action == "bulk_delete" and selected_ids:
                # Coerce IDs safely
                try:
                    ids = [int(x) for x in selected_ids]
                except Exception:
                    ids = [int(x) for x in selected_ids if str(x).isdigit()]

                if not ids:
                    flash("No valid rows selected.", "warning")
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                q = select(DirectImageUpload).where(DirectImageUpload.id.in_(ids))
                q = scope(db_session, q, DirectImageUpload, current_user, 'upload.direct.view')

                if not can_manage_others:
                    q = q.where(DirectImageUpload.uploader_id == current_user.id)
                    
                rows = db_session.execute(q).scalars().all()

                # Check for grading tasks before deletion
                upload_ids = [u.id for u in rows]
                tasks_by_upload: dict[int, list[GradingTask]] = {}
                if upload_ids:
                    task_rows = db_session.execute(
                        select(GradingTask).where(GradingTask.direct_image_upload_id.in_(upload_ids))
                    ).scalars().all()
                    for task in task_rows:
                        if task.direct_image_upload_id is None:
                            continue
                        tasks_by_upload.setdefault(task.direct_image_upload_id, []).append(task)

                blocked_uploads: list[tuple[DirectImageUpload, list[GradingTask]]] = []
                deletable_uploads: list[DirectImageUpload] = []
                for u in rows:
                    related_tasks = tasks_by_upload.get(u.id, [])
                    if any(task.state != 'pending' for task in related_tasks):
                        blocked_uploads.append((u, related_tasks))
                    else:
                        deletable_uploads.append(u)

                if blocked_uploads and not deletable_uploads:
                    # All uploads are blocked, abort entirely
                    skipped_payload = [
                        {
                            "upload_id": upload.id,
                            "filename": upload.filename,
                            "non_pending_states": sorted(
                                {task.state for task in related_tasks if task.state != 'pending'}
                            ),
                        }
                        for upload, related_tasks in blocked_uploads
                    ]
                    editing_logger.warning(
                        "Bulk delete aborted; all uploads blocked=%s user_id=%s",
                        [item["upload_id"] for item in skipped_payload],
                        current_user.id,
                    )
                    
                    # Build detailed error message for user
                    blocked_details = []
                    for upload, related_tasks in blocked_uploads:
                        non_pending_states = sorted({task.state for task in related_tasks if task.state != 'pending'})
                        blocked_details.append(
                            f"Image '{upload.filename}' has tasks in states: {', '.join(non_pending_states)}"
                        )
                    
                    flash(
                        f"Cannot delete {len(blocked_uploads)} image(s) with active grading tasks. "
                        f"{' '.join(blocked_details)}",
                        "danger"
                    )
                    return redirect(url_for("direct_uploads.dashboard"), code=303)
                elif blocked_uploads and deletable_uploads:
                    # Some uploads blocked, but we can proceed with deletable ones
                    skipped_payload = [
                        {
                            "upload_id": upload.id,
                            "filename": upload.filename,
                            "non_pending_states": sorted(
                                {task.state for task in related_tasks if task.state != 'pending'}
                            ),
                        }
                        for upload, related_tasks in blocked_uploads
                    ]
                    editing_logger.warning(
                        "Bulk delete partially blocked; uploads blocked=%s proceeding=%s user_id=%s",
                        [item["upload_id"] for item in skipped_payload],
                        [u.id for u in deletable_uploads],
                        current_user.id,
                    )
                    
                    # Build warning message for user about blocked uploads
                    blocked_details = []
                    for upload, related_tasks in blocked_uploads:
                        non_pending_states = sorted({task.state for task in related_tasks if task.state != 'pending'})
                        blocked_details.append(
                            f"Image '{upload.filename}' has tasks in states: {', '.join(non_pending_states)}"
                        )
                    
                    flash(
                        f"Skipping {len(blocked_uploads)} image(s) with active grading tasks. "
                        f"{' '.join(blocked_details)} "
                        f"Proceeding with {len(deletable_uploads)} deletable image(s).",
                        "warning"
                    )

                deleted_files = 0
                deleted_rows = 0

                for u in deletable_uploads:
                    # Try to delete edited first (if present)
                    if getattr(u, "edited_filename", None):
                        try:
                            ep = abs_from_parts(u.folder_rel, u.edited_filename, "edited")
                            if ep.exists():
                                ep.unlink()
                                deleted_files += 1
                            else:
                                editing_logger.info(
                                    "Edited file missing on disk; will still delete DB row. upload_id=%s path=%s",
                                    u.id, ep
                                )
                        except Exception as e:
                            editing_logger.warning(
                                "Failed to delete edited file for upload_id=%s (folder_rel=%r, edited_filename=%r): %s",
                                u.id, u.folder_rel, u.edited_filename, e
                            )

                    # Then delete original
                    try:
                        op = abs_from_parts(u.folder_rel, u.filename, "orig")
                        if op.exists():
                            op.unlink()
                            deleted_files += 1
                        else:
                            editing_logger.info(
                                "Original file missing on disk; will still delete DB row. upload_id=%s path=%s",
                                u.id, op
                            )
                    except Exception as e:
                        editing_logger.warning(
                            "Failed to delete original file for upload_id=%s (folder_rel=%r, filename=%r): %s",
                            u.id, u.folder_rel, u.filename, e
                        )

                    # Collect all upload IDs that will be deleted
                deleted_upload_ids = [u.id for u in deletable_uploads]

                # Delete pending grading tasks FIRST (before deleting the uploads)
                deleted_task_count = 0
                if deleted_upload_ids:
                    # Check for ANY tasks referencing these uploads (not just pending ones)
                    all_referencing_tasks = db_session.execute(
                        select(GradingTask).where(
                            GradingTask.direct_image_upload_id.in_(deleted_upload_ids)
                        )
                    ).scalars().all()

                    for task in all_referencing_tasks:
                        # Only delete tasks that are pending or completed (not active ones)
                        if task.state in ('pending', 'completed', 'error'):
                            db_session.delete(task)
                            deleted_task_count += 1
                            editing_logger.info(
                                "Deleted %s grading task (state=%s) for upload_id=%s before deletion",
                                sanitize_log_value(task.id),
                                sanitize_log_value(task.state),
                                sanitize_log_value(task.direct_image_upload_id),
                            )
                        else:
                            editing_logger.warning(
                                "Cannot delete upload_id=%s: grading task %s has state='%s'",
                                sanitize_log_value(task.direct_image_upload_id),
                                sanitize_log_value(task.id),
                                sanitize_log_value(task.state),
                            )

                    if deleted_task_count > 0:
                        editing_logger.info(
                            "Deleted %s grading tasks (pending/completed) for removed images by user_id=%s",
                            sanitize_log_value(deleted_task_count),
                            sanitize_log_value(current_user.id),
                        )

                # Now clean up associated thumbnails
                for u in deletable_uploads:
                    try:
                        thumbnail_results = add_thumbnail_cleanup_to_direct_upload_deletion(u, editing_logger)
                        if thumbnail_results['original_deleted']:
                            editing_logger.info(
                                "Deleted original thumbnail for upload_id=%s",
                                sanitize_log_value(u.id),
                            )
                        if thumbnail_results['edited_deleted']:
                            editing_logger.info(
                                "Deleted edited thumbnail for upload_id=%s",
                                sanitize_log_value(u.id),
                            )
                        if thumbnail_results['errors']:
                            for error in thumbnail_results['errors']:
                                editing_logger.warning(
                                    "Thumbnail cleanup error for upload_id=%s: %s",
                                    sanitize_log_value(u.id),
                                    sanitize_log_value(error),
                                )
                    except Exception as e:
                        editing_logger.warning(
                            "Failed to clean up thumbnails for upload_id=%s: %s",
                            sanitize_log_value(u.id),
                            sanitize_log_value(e),
                        )

                # Finally delete the DirectImageUpload records (now safe)
                for u in deletable_uploads:
                    db_session.delete(u)
                    deleted_rows += 1

                db_session.commit()
                editing_logger.info(
                    "Bulk delete removed %s record(s), %s file(s), and %s pending task(s) by user_id=%s",
                    sanitize_log_value(deleted_rows),
                    sanitize_log_value(deleted_files),
                    sanitize_log_value(deleted_task_count),
                    sanitize_log_value(current_user.id),
                )
                
                # Success message (we already showed warning about blocked uploads if needed)
                if deleted_task_count > 0:
                    flash(f"Deleted {deleted_rows} record(s). Removed {deleted_files} file(s) and {deleted_task_count} pending task(s).", "success")
                else:
                    flash(f"Deleted {deleted_rows} record(s). Removed {deleted_files} file(s).", "success")
                return redirect(url_for("direct_uploads.dashboard"), code=303)


            else:
                flash("No uploads selected for operation.", "warning")

            return redirect(url_for("direct_uploads.dashboard"), code=303)

        # GET (filters + pagination)
        page     = request.args.get('page', 1, type=int)
        per_page = 50

        # keep dates as strings (do NOT _to_int these)
        f_date_from   = request.args.get('date_from')
        f_date_to     = request.args.get('date_to')
        f_lab_unit_id = _to_int(request.args.get('lab_unit_id'))
        f_uploader_id = _to_int(request.args.get('uploader_id'))
        f_hospital_id = _to_int(request.args.get('hospital_id'))
        f_camera_id   = _to_int(request.args.get('camera_id'))
        f_disease_id  = _to_int(request.args.get('disease_id'))
        f_area_id     = _to_int(request.args.get('area_id'))
        f_pregraded   = request.args.get('pregraded')

        if page < 1:
            page = 1

        q = select(DirectImageUpload)
        q = scope(db_session, q, DirectImageUpload, current_user, 'upload.direct.view')
        
        # Date filters
        if f_date_from:
            try:
                start_dt = datetime.strptime(f_date_from, '%Y-%m-%d')
                q = q.where(DirectImageUpload.created_at >= start_dt)
            except ValueError:
                pass
        if f_date_to:
            try:
                end_dt = datetime.strptime(f_date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                q = q.where(DirectImageUpload.created_at <= end_dt)
            except ValueError:
                pass

        # ID filters
        if f_lab_unit_id is not None:
            q = q.where(DirectImageUpload.lab_unit_id == f_lab_unit_id)
        if f_hospital_id is not None:
            q = q.where(DirectImageUpload.hospital_id == f_hospital_id)
        if f_camera_id is not None:
            q = q.where(DirectImageUpload.camera_id == f_camera_id)
        if f_disease_id is not None:
            q = q.where(DirectImageUpload.disease_id == f_disease_id)
        if f_area_id is not None:
            q = q.where(DirectImageUpload.area_id == f_area_id)
        if f_pregraded == "yes":
            q = q.where(DirectImageUpload.is_pregraded.is_(True))
        elif f_pregraded == "no":
            q = q.where(DirectImageUpload.is_pregraded.is_(False))

        # RBAC: only managers/admins can filter by uploader; others are scoped by lab-unit and ownership
        if can_manage_others and f_uploader_id is not None:
            q = q.where(DirectImageUpload.uploader_id == f_uploader_id)

        # ---- Build filtered ID subquery (no ORDER BY here) ----
        filtered_ids_sq = (
            q.with_only_columns(DirectImageUpload.id)  # SELECT id FROM (filtered)
            .order_by(None)
            .subquery()
        )

        # Count from filtered set
        total_count = db_session.execute(
            select(func.count()).select_from(filtered_ids_sq)
        ).scalar_one()

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        if page > total_pages:
            page = max(total_pages, 1)

        # ---- Page rows: JOIN back to entity on id (prevents duplicates) ----
        main_q = (
            select(DirectImageUpload)
            .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
            .order_by(DirectImageUpload.created_at.desc(), DirectImageUpload.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        uploads = db_session.execute(main_q).scalars().all()

        upload_ids = [u.id for u in uploads]
        # Fetch associated verification remarks (includes dataset labels for pre-graded)
        verification_map: dict[int, str] = {}
        if upload_ids:
            verification_rows = db_session.execute(
                select(DirectImageVerify.image_upload_id, DirectImageVerify.remarks)
                .where(DirectImageVerify.image_upload_id.in_(upload_ids))
            ).all()
            for image_upload_id, remarks in verification_rows:
                if remarks:
                    verification_map[image_upload_id] = remarks

        # Fetch gradings for these uploads using Grade model instead of ImageGrading
        gradings = {}
        if upload_ids:
            # Query Grade records through GradingTask for these uploads
            grading_rows = db_session.execute(
                select(Grade)
                .join(GradingTask, Grade.task_id == GradingTask.id)
                .where(GradingTask.direct_image_upload_id.in_(upload_ids))
            ).scalars().all()

            # Group gradings by upload_id (from task)
            for grade in grading_rows:
                upload_id = grade.task.direct_image_upload_id
                if upload_id not in gradings:
                    gradings[upload_id] = []
                gradings[upload_id].append(grade)

        # Compute task states for each upload to gate image-edit actions
        upload_task_states: dict[int, set[str]] = {}
        upload_has_non_pending_task: dict[int, bool] = {}
        if upload_ids:
            task_rows = db_session.execute(
                select(GradingTask.direct_image_upload_id, GradingTask.state)
                .where(
                    GradingTask.direct_image_upload_id.in_(upload_ids),
                    GradingTask.direct_image_upload_id.is_not(None),
                )
            ).all()
            for upload_id, state in task_rows:
                if upload_id is None:
                    continue
                states = upload_task_states.setdefault(upload_id, set())
                if state:
                    states.add(state)

            for upload_id, states in upload_task_states.items():
                upload_has_non_pending_task[upload_id] = any(state != "pending" for state in states)

        # Side lookups for the current page
        ids = lambda attr: {getattr(u, attr) for u in uploads}
        hospitals = {h.id: h for h in db_session.execute(select(Hospital).where(Hospital.id.in_(ids("hospital_id")))).scalars().all()} if uploads else {}
        lab_units = {l.id: l for l in db_session.execute(select(LabUnit).where(LabUnit.id.in_(ids("lab_unit_id")))).scalars().all()} if uploads else {}
        cameras   = {c.id: c for c in db_session.execute(select(Camera).where(Camera.id.in_(ids("camera_id")))).scalars().all()} if uploads else {}
        diseases  = {d.id: d for d in db_session.execute(select(Disease).where(Disease.id.in_(ids("disease_id")))).scalars().all()} if uploads else {}
        areas     = {a.id: a for a in db_session.execute(select(Area).where(Area.id.in_(ids("area_id")))).scalars().all()} if uploads else {}
        users     = {u.id: u for u in db_session.execute(select(User).where(User.id.in_({u.uploader_id for u in uploads}))).scalars().all()} if uploads else {}

        # Full lists for filters - use scoped query to determine what user can see
        # Build a scoped query to get all accessible lab units and hospitals
        scoped_lab_units_q = select(LabUnit)
        scoped_lab_units_q = scope(db_session, scoped_lab_units_q, LabUnit, current_user, 'upload.direct.view')
        all_lab_units = db_session.execute(scoped_lab_units_q.order_by(LabUnit.name)).scalars().all()
        
        # Get hospitals from accessible lab units
        accessible_hospital_ids = {lu.hospital_id for lu in all_lab_units if lu.hospital_id is not None}
        all_hospitals = db_session.execute(
            select(Hospital).where(Hospital.id.in_(accessible_hospital_ids)).order_by(Hospital.name)
        ).scalars().all() if accessible_hospital_ids else []
        
        all_cameras   = db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        all_diseases  = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
        all_areas     = db_session.execute(select(Area).order_by(Area.name)).scalars().all()
        all_users     = db_session.execute(select(User).order_by(User.username)).scalars().all()

        # ---- KPIs from the SAME filtered set (join on id) ----
        kpi_total_uploads = total_count

        camera_kpis = {
            name: cnt for name, cnt in db_session.execute(
                select(Camera.name, func.count())
                .join(DirectImageUpload, DirectImageUpload.camera_id == Camera.id)
                .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
                .group_by(Camera.name)
            ).all()
        }
        disease_kpis = {
            name: cnt for name, cnt in db_session.execute(
                select(Disease.name, func.count())
                .join(DirectImageUpload, DirectImageUpload.disease_id == Disease.id)
                .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
                .group_by(Disease.name)
            ).all()
        }
        area_kpis = {
            name: cnt for name, cnt in db_session.execute(
                select(Area.name, func.count())
                .join(DirectImageUpload, DirectImageUpload.area_id == Area.id)
                .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
                .group_by(Area.name)
            ).all()
        }

        # Build hierarchical KPI of counts by hospital -> lab unit -> disease
        hospital_lab_disease_rows = db_session.execute(
            select(
                Hospital.id.label("hospital_id"),
                Hospital.name.label("hospital_name"),
                LabUnit.id.label("lab_unit_id"),
                LabUnit.name.label("lab_unit_name"),
                Disease.name.label("disease_name"),
                func.count().label("image_count"),
            )
            .select_from(DirectImageUpload)
            .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
            .join(LabUnit, DirectImageUpload.lab_unit_id == LabUnit.id)
            .join(Hospital, LabUnit.hospital_id == Hospital.id)
            .join(Disease, DirectImageUpload.disease_id == Disease.id)
            .group_by(
                Hospital.id,
                Hospital.name,
                LabUnit.id,
                LabUnit.name,
                Disease.name,
            )
            .order_by(Hospital.name, LabUnit.name, Disease.name)
        ).all()

        hospital_lab_unit_disease_kpis: list[dict[str, object]] = []
        hospital_index: dict[int, dict[str, object]] = {}
        lab_index: dict[int, dict[int, dict[str, object]]] = {}

        for row in hospital_lab_disease_rows:
            hosp_entry = hospital_index.get(row.hospital_id)
            if hosp_entry is None:
                hosp_entry = {
                    "hospital_id": row.hospital_id,
                    "hospital_name": row.hospital_name,
                    "lab_units": [],
                }
                hospital_index[row.hospital_id] = hosp_entry
                hospital_lab_unit_disease_kpis.append(hosp_entry)

            lab_map = lab_index.setdefault(row.hospital_id, {})
            lab_entry = lab_map.get(row.lab_unit_id)
            if lab_entry is None:
                lab_entry = {
                    "lab_unit_id": row.lab_unit_id,
                    "lab_unit_name": row.lab_unit_name,
                    "diseases": [],
                }
                lab_map[row.lab_unit_id] = lab_entry
                hosp_entry["lab_units"].append(lab_entry)

            lab_entry["diseases"].append(
                {
                    "disease_name": row.disease_name,
                    "image_count": row.image_count,
                }
            )

        bulk_edit_result = session.pop('bulk_edit_result', None)

        current_app.logger.info(
            "Dashboard accessed by %s (%s). Page:%s Total:%s",
            current_user.username, current_user.id, page, total_count
        )

        return render_template(
            "direct_uploads/dashboard.html",
            uploads=uploads,
            gradings=gradings,
            hospitals=hospitals, lab_units=lab_units, cameras=cameras,
            diseases=diseases, areas=areas, users=users,
            all_hospitals=all_hospitals, all_lab_units=all_lab_units,
            all_cameras=all_cameras, all_diseases=all_diseases, all_areas=all_areas, all_users=all_users,
            current_page=page, total_pages=total_pages,
            total_count=total_count, per_page=per_page,
            kpi_total_uploads=kpi_total_uploads,
            camera_kpis=camera_kpis, disease_kpis=disease_kpis, area_kpis=area_kpis,
            hospital_lab_unit_disease_kpis=hospital_lab_unit_disease_kpis,
            filter_date_from=f_date_from, filter_date_to=f_date_to,
            filter_lab_unit_id=f_lab_unit_id, filter_uploader_id=f_uploader_id,
            filter_hospital_id=f_hospital_id, filter_camera_id=f_camera_id,
            filter_disease_id=f_disease_id, filter_area_id=f_area_id, filter_pregraded=f_pregraded,
            verification_map=verification_map,
            bulk_edit_result=bulk_edit_result,
            upload_has_non_pending_task=upload_has_non_pending_task,
            upload_task_states=upload_task_states,
        )
