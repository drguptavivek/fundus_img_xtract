import logging
import traceback
from pathlib import Path
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, current_app, url_for as flask_url_for, jsonify
from flask_login import current_user
from werkzeug.exceptions import NotFound
from . import bp
from utils.utils import with_session, require_owner_or_roles
from auth.roles import roles_required
from sqlalchemy import select
from models import DirectImageUpload, Hospital, LabUnit, Camera, Disease, Area, User, GradingTask
from utils.fileUtils import abs_from_parts


editing_logger = logging.getLogger("editing")

def _normalize_task_state(state: str | None) -> str:
    """Return a canonical lowercase task state for comparisons."""
    if state is None:
        return ""
    if not isinstance(state, str):
        return str(state).strip().lower()
    return state.strip().lower()


def _safe_text(value: object) -> str:
    """Convert a value into a safe string for logging."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _log_allowed_edit(upload: DirectImageUpload, task_states: list[str]) -> None:
    """Record that an edit session was permitted for the given upload."""
    log_location = current_app.config.get("DIRECT_IMAGE_EDIT_LOG", "logs/direct_image_edit.log")
    log_path = Path(log_location)
    if not log_path.is_absolute():
        log_path = Path(current_app.root_path) / log_path

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        editing_logger.error(
            "Unable to ensure edit log directory %s exists: %s",
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
    raw_normalized = [_normalize_task_state(state) for state in task_states]
    normalized_states = sorted({
        _safe_text(state) for state in raw_normalized if state
    })
    states_joined = ",".join(normalized_states) if normalized_states else "none"
    line = "\t".join(
        [
            timestamp,
            f"event=edit_image_allowed",
            f"user={user_identifier}",
            f"upload_id={upload.id}",
            f"filename={upload.filename}",
            f"task_states={states_joined}",
        ]
    ) + "\n"

    try:
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(line)
    except OSError as exc:
        editing_logger.error(
            "Failed to append edit log for upload_id=%s at %s: %s",
            upload.id,
            log_path,
            exc,
        )

@bp.route("/direct/upload/edit_image/<int:upload_id>", methods=["GET"])
@roles_required('fileUploader', 'optometrist', 'data_manager', 'admin')
def edit_image(upload_id: int):
    with with_session() as db:
        try:
            upload = db.get(DirectImageUpload, upload_id)
            if not upload:
                flash("Upload not found.", "danger")
                return redirect(flask_url_for("direct_uploads.dashboard"))

            if not require_owner_or_roles(upload, 'admin', 'data_manager'):
                flash("You don't have permission to edit this upload.", "danger")
                return redirect(flask_url_for("direct_uploads.dashboard"))

            raw_states = db.execute(
                select(GradingTask.state).where(GradingTask.direct_image_upload_id == upload.id)
            ).scalars().all()
            normalized_states = [_normalize_task_state(state) for state in raw_states]
            non_pending_states = sorted({state for state in normalized_states if state and state != 'pending'})
            if non_pending_states:
                states_list = ", ".join(non_pending_states)
                editing_logger.warning(
                    "Direct image edit blocked for upload_id=%s by user_id=%s due to task states: %s",
                    upload.id,
                    current_user.id if current_user.is_authenticated else "anonymous",
                    states_list,
                )
                flash(
                    "Editing blocked. Grading tasks already in progress: "
                    f"{states_list}.",
                    "danger",
                )
                return redirect(flask_url_for("direct_uploads.dashboard"))

            _log_allowed_edit(upload, normalized_states)

            has_edited_version = bool(upload.edited_filename)
            if has_edited_version:
                image_url = flask_url_for("media._directImgEdByUUID", uuid_str=upload.uuid)
                editing_logger.info("Loading EDITED image %s for editing", upload_id)
            else:
                image_url = flask_url_for("media._directImgOrigByUUID", uuid_str=upload.uuid)
                editing_logger.info("Loading ORIGINAL image %s for editing", upload_id)

            hospital = db.get(Hospital, upload.hospital_id)
            lab_unit = db.get(LabUnit, upload.lab_unit_id)
            camera   = db.get(Camera, upload.camera_id)
            disease  = db.get(Disease, upload.disease_id)
            area     = db.get(Area, upload.area_id)
            uploader = db.get(User, upload.uploader_id)

            return render_template("direct_uploads/edit_image.html",
                                   upload=upload, hospital=hospital, lab_unit=lab_unit,
                                   camera=camera, disease=disease, area=area,
                                   uploader=uploader, image_url=image_url,
                                   has_edited_version=has_edited_version)
        except FileNotFoundError as e:
            editing_logger.error("Missing file for upload_id=%s at %s", upload_id, e)
            flash("Image file not found on server.", "danger")
            return redirect(flask_url_for("direct_uploads.dashboard"))
        except Exception:
            editing_logger.error("Error loading image editor for upload %s:\n%s",
                                     upload_id, traceback.format_exc())
            flash("An error occurred while loading the image editor.", "danger")
            return redirect(flask_url_for("direct_uploads.dashboard"))

@bp.route("/direct/upload/restore_original/<int:upload_id>", methods=["POST"])
@roles_required('fileUploader', 'optometrist', 'data_manager', 'admin')
def restore_original(upload_id: int):
    with with_session() as db:
        try:
            upload = db.get(DirectImageUpload, upload_id)
            if not upload:
                return jsonify({"error": "Upload not found."}), 404

            if not require_owner_or_roles(upload, 'admin', 'data_manager'):
                return jsonify({"error": "Permission denied."}), 403

            raw_states = db.execute(
                select(GradingTask.state).where(GradingTask.direct_image_upload_id == upload.id)
            ).scalars().all()
            normalized_states = [_normalize_task_state(state) for state in raw_states]
            if any(state and state != 'pending' for state in normalized_states):
                editing_logger.warning(
                    "Restore original blocked for upload_id=%s by user_id=%s due to task states: %s",
                    upload.id,
                    current_user.id if current_user.is_authenticated else "anonymous",
                    sorted({state for state in normalized_states if state and state != 'pending'}),
                )
                return jsonify({"error": "Cannot modify image while associated grading tasks are in progress."}), 409

            if not upload.edited_filename:
                return jsonify({"message": "No edited version to restore."}), 200

            # Delete the edited file
            edited_path = abs_from_parts(upload.folder_rel, upload.edited_filename, kind="edited")
            try:
                edited_path.unlink()
                editing_logger.info("Deleted edited file: %s", edited_path)
            except FileNotFoundError:
                editing_logger.warning("Edited file not found at %s, but proceeding to clear from DB.", edited_path)
            
            # Update the database
            upload.edited_filename = None
            db.commit()

            flash("Original image has been restored.", "success")
            return jsonify({"message": "Original image restored.", "redirect_url": flask_url_for('direct_uploads.edit_image', upload_id=upload_id)}), 200

        except Exception as e:
            db.rollback()
            editing_logger.error("Error restoring original for upload %s:\n%s",
                                     upload_id, traceback.format_exc())
            return jsonify({"error": "An unexpected error occurred."}), 500
