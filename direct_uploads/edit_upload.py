# direct_uploads/edit_upload.py

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from utils.fileUtils import abs_from_parts

from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from models import (
    DirectImageUpload,
    Hospital,
    LabUnit,
    Camera,
    Disease,
    Area,
    User,
    GradingTask,
    utcnow,
)

editing_logger = logging.getLogger("editing")


def _normalize_task_state(state):
    if state is None:
        return ""
    if not isinstance(state, str):
        return str(state).strip().lower()
    return state.strip().lower()


def _safe_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _log_image_attribute_changes(upload: DirectImageUpload, changes):
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

    lines = []
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


def _to_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _require_entity(db, model, pk: int | None, label: str):
    """Fetch entity or raise a ValueError with a friendly message."""
    if not pk:
        raise ValueError(f"Missing {label}")
    obj = db.get(model, pk)
    if not obj:
        raise ValueError(f"Invalid {label}")
    return obj


@bp.route("/direct/upload/edit/<int:upload_id>", methods=["GET", "POST"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin")
def edit_upload(upload_id):
    with get_db_session() as db:
        upload = db.get(DirectImageUpload, upload_id)
        if not upload:
            flash("Upload not found.", "danger")
            return redirect(url_for("direct_uploads.dashboard"))

        # Try to reconstruct the on-disk file path for display (read-only)
        try:
            file_path = abs_from_parts(upload.folder_rel, upload.filename, kind="orig")
        except Exception:
            file_path = None

        is_admin = current_user.has_role("admin")
        is_manager = current_user.has_role("data_manager")
        can_choose_any = is_admin or is_manager

        # can edit if admin/manager OR owner
        if not (can_choose_any or upload.uploader_id == current_user.id):
            flash("You don't have permission to edit this upload.", "danger")
            return redirect(url_for("direct_uploads.dashboard"))

        task_rows = db.execute(
            select(GradingTask).where(GradingTask.direct_image_upload_id == upload.id)
        ).scalars().all()
        normalized_task_states = [_normalize_task_state(task.state) for task in task_rows]
        non_pending_states = sorted({state for state in normalized_task_states if state and state != "pending"})
        if non_pending_states:
            states_list = ", ".join(non_pending_states)
            editing_logger.warning(
                "Edit metadata blocked for upload_id=%s by user_id=%s due to task states: %s",
                upload.id,
                current_user.id if current_user.is_authenticated else "anonymous",
                states_list,
            )
            flash(
                "Editing blocked. Grading tasks already in progress: "
                f"{states_list}.",
                "danger",
            )
            return redirect(url_for("direct_uploads.dashboard"))

        pending_tasks = [task for task, state in zip(task_rows, normalized_task_states) if state == "pending"]

        # Build allowed sets for users without elevated privileges
        allowed_lab_unit_ids = set()
        allowed_hospital_ids = set()
        if not can_choose_any:
            user_db = db.execute(
                select(User)
                .options(selectinload(User.lab_units))
                .where(User.id == current_user.id)
            ).scalar_one()
            allowed_lab_unit_ids = {lu.id for lu in user_db.lab_units}
            allowed_hospital_ids = {lu.hospital_id for lu in user_db.lab_units}

        if request.method == "POST":
            req = request.form

            hid = _to_int(req.get("hospital_id"))
            lid = _to_int(req.get("lab_unit_id"))
            cid = _to_int(req.get("camera_id"))
            did = _to_int(req.get("disease_id"))
            aid = _to_int(req.get("area_id"))
            is_mydriatic = req.get("is_mydriatic") == "on"

            if not all([hid, lid, cid, did, aid]):
                flash("All fields are required.", "danger")
                return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id), code=303)

            # RBAC: restricted users must stay within their own assignments
            if not can_choose_any:
                if lid not in allowed_lab_unit_ids or hid not in allowed_hospital_ids:
                    flash("You cannot assign this hospital or lab unit.", "danger")
                    return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id), code=303)

            # Validate entities robustly
            try:
                hospital = _require_entity(db, Hospital, hid, "Hospital")
                lab_unit = _require_entity(db, LabUnit, lid, "Lab Unit")
                camera = _require_entity(db, Camera, cid, "Camera")
                disease = _require_entity(db, Disease, did, "Disease")
                area = _require_entity(db, Area, aid, "Area")
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id), code=303)

            # Consistency: lab unit must belong to selected hospital
            if lab_unit.hospital_id != hospital.id:
                flash("Selected Lab Unit does not belong to the selected Hospital.", "danger")
                return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id), code=303)

            # Immutable fields: do NOT accept filename/folder_rel changes from form (defense-in-depth)
            # Any rogue form fields will be ignored.

            # Prepare audit log (before/after)
            before = dict(
                hospital_id=upload.hospital_id,
                lab_unit_id=upload.lab_unit_id,
                camera_id=upload.camera_id,
                disease_id=upload.disease_id,
                area_id=upload.area_id,
                is_mydriatic=upload.is_mydriatic,
            )

            # Apply updates
            field_changes = []
            if upload.hospital_id != hospital.id:
                field_changes.append(
                    {
                        "field": "Hospital",
                        "old": getattr(upload.hospital, "name", str(upload.hospital_id)),
                        "new": hospital.name,
                    }
                )
                upload.hospital_id = hospital.id
            if upload.lab_unit_id != lab_unit.id:
                field_changes.append(
                    {
                        "field": "Lab Unit",
                        "old": getattr(upload.lab_unit, "name", str(upload.lab_unit_id)),
                        "new": lab_unit.name,
                    }
                )
                upload.lab_unit_id = lab_unit.id
            if upload.camera_id != camera.id:
                field_changes.append(
                    {
                        "field": "Camera",
                        "old": getattr(upload.camera, "name", str(upload.camera_id)),
                        "new": camera.name,
                    }
                )
                upload.camera_id = camera.id
            if upload.disease_id != disease.id:
                field_changes.append(
                    {
                        "field": "Disease",
                        "old": getattr(upload.disease, "name", str(upload.disease_id)),
                        "new": disease.name,
                    }
                )
                upload.disease_id = disease.id
            if upload.area_id != area.id:
                field_changes.append(
                    {
                        "field": "Area",
                        "old": getattr(upload.area, "name", str(upload.area_id)),
                        "new": area.name,
                    }
                )
                upload.area_id = area.id
            if upload.is_mydriatic != is_mydriatic:
                field_changes.append(
                    {
                        "field": "Mydriatic",
                        "old": "Yes" if upload.is_mydriatic else "No",
                        "new": "Yes" if is_mydriatic else "No",
                    }
                )
                upload.is_mydriatic = is_mydriatic

            after = dict(
                hospital_id=upload.hospital_id,
                lab_unit_id=upload.lab_unit_id,
                camera_id=upload.camera_id,
                disease_id=upload.disease_id,
                area_id=upload.area_id,
                is_mydriatic=upload.is_mydriatic,
            )

            updated_task_ids = []
            for task in pending_tasks:
                task_changed = False
                if task.lab_unit_id != upload.lab_unit_id:
                    task.lab_unit_id = upload.lab_unit_id
                    task_changed = True
                if task.disease_id != upload.disease_id:
                    task.disease_id = upload.disease_id
                    task_changed = True
                if task_changed:
                    task.updated_at = utcnow()
                    updated_task_ids.append(task.id)

            db.commit()

            _log_image_attribute_changes(upload, field_changes)

            editing_logger.info(
                "Upload %s metadata edited by %s (%s) from %s to %s",
                upload.id,
                current_user.username,
                current_user.id,
                before,
                after,
            )
            if updated_task_ids:
                editing_logger.info(
                    "Updated pending grading tasks %s after edit of upload %s",
                    updated_task_ids,
                    upload.id,
                )

            flash(
                "Upload metadata updated successfully." if not updated_task_ids else
                f"Upload metadata updated successfully. Pending tasks updated: {len(updated_task_ids)}.",
                "success",
            )
            return redirect(url_for("direct_uploads.dashboard"), code=303)

        # GET options: admins/managers see all; restricted users see only their own
        if can_choose_any:
            hospitals = db.scalars(select(Hospital).order_by(Hospital.name)).all()
            lab_units = db.scalars(select(LabUnit).order_by(LabUnit.name)).all()
        else:
            hospitals = db.scalars(
                select(Hospital)
                .where(Hospital.id.in_(allowed_hospital_ids))
                .order_by(Hospital.name)
            ).all()
            lab_units = db.scalars(
                select(LabUnit)
                .where(LabUnit.id.in_(allowed_lab_unit_ids))
                .order_by(LabUnit.name)
            ).all()

        cameras = db.scalars(select(Camera).order_by(Camera.name)).all()
        diseases = db.scalars(select(Disease).order_by(Disease.name)).all()
        areas = db.scalars(select(Area).order_by(Area.name)).all()

        return render_template(
            "direct_uploads/edit_upload.html",
            upload=upload,
            file_path=file_path,                  # helpful read-only context in UI
            can_choose_any=can_choose_any,        # template can adjust scope/help text
            hospitals=hospitals,
            lab_units=lab_units,
            cameras=cameras,
            diseases=diseases,
            areas=areas,
        )
