import traceback
import logging
from pathlib import Path
from flask import request, jsonify, current_app, session
from flask_login import current_user
from sqlalchemy import select
from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from models import DirectImageUpload, BASE_DIR, GradingTask, ImagePiiVerification
from utils.fileUtils import abs_from_parts
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.log_sanitize import sanitize_log_value
from utils.sensitive_operations import _log_sensitive_operation
from utils.media_cache import bump_media_cache_version
from utils.image_edit_payload import InvalidImageEditPayload, decode_image_edit_payload


editing_logger = logging.getLogger("editing")


def _normalize_task_state(state):
    if state is None:
        return ""
    if not isinstance(state, str):
        return str(state).strip().lower()
    return state.strip().lower()

@bp.route("/direct/upload/save_image/<int:upload_id>", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def save_edited_image(upload_id: int):
    with get_db_session() as db:
        try:
            editing_logger.info(
                "Save image request for upload_id=%s",
                sanitize_log_value(upload_id),
            )
            editing_logger.info(
                "Content-Type: %s",
                sanitize_log_value(request.content_type),
            )

            upload = db.get(DirectImageUpload, upload_id)
            if not upload:
                editing_logger.warning(
                    "Upload not found for id: %s",
                    sanitize_log_value(upload_id),
                )
                return jsonify({"error": "Upload not found."}), 404

            allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
            can_manage_others = current_user.has_role(
                "admin", "data_manager", "local_admin", "fileUploader", "optometrist"
            )

            if upload.lab_unit_id not in allowed_lab_unit_ids:
                editing_logger.warning(
                    "User %s lacks lab unit access for %s",
                    sanitize_log_value(current_user.id),
                    sanitize_log_value(upload_id),
                )
                return jsonify({"error": "You don't have permission to edit this upload."}), 403

            if not (can_manage_others or upload.uploader_id == current_user.id):
                editing_logger.warning(
                    "User %s lacks permission to edit %s",
                    sanitize_log_value(current_user.id),
                    sanitize_log_value(upload_id),
                )
                return jsonify({"error": "You don't have permission to edit this upload."}), 403

            task_states = db.execute(
                select(GradingTask.state).where(GradingTask.direct_image_upload_id == upload.id)
            ).scalars().all()
            has_non_pending = any(_normalize_task_state(state) not in ("", "pending") for state in task_states)
            payload = request.get_json(silent=True) if request.is_json else None
            allow_graded_edit = False
            if payload is not None:
                allow_graded_edit = bool(payload.get("allow_graded_edit"))
            else:
                allow_graded_edit = (request.form.get("allow_graded_edit") or "").lower() == "true"
            override_allowed = allow_graded_edit and session.get("anonymize_edit_uuid") == str(upload.uuid)
            if has_non_pending and not override_allowed:
                editing_logger.warning(
                    "Save blocked for upload %s due to task states %s",
                    sanitize_log_value(upload_id),
                    sanitize_log_value(task_states),
                )
                return jsonify({"error": "Cannot edit image while grading tasks are in progress."}), 409

            image_data = payload.get('image_data') if payload is not None else request.form.get('image_data')
            if not image_data:
                editing_logger.warning(
                    "No image data for upload %s",
                    sanitize_log_value(upload_id),
                )
                return jsonify({"error": "No image data provided."}), 400

            try:
                decoded_image = decode_image_edit_payload(image_data)
                image_bytes = decoded_image.content
            except InvalidImageEditPayload as e:
                editing_logger.error(
                    "Invalid edited image payload for upload %s: %s",
                    sanitize_log_value(upload_id),
                    sanitize_log_value(e),
                )
                return jsonify({"error": "Invalid image data provided."}), 400

            # Correctly determine the path for the new edited file
            previous_edited_filename = upload.edited_filename
            previous_thumbnail_filename = upload.edited_thumbnail_filename
            edited_basename = f"edited_{Path(upload.filename).stem}{decoded_image.extension}"
            edited_path = abs_from_parts(upload.folder_rel, edited_basename, kind="edited")
            
            # Ensure the destination directory exists
            edited_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the new edited image
            edited_path.write_bytes(image_bytes)
            if previous_edited_filename and previous_edited_filename != edited_basename:
                abs_from_parts(
                    upload.folder_rel,
                    previous_edited_filename,
                    kind="edited",
                ).unlink(missing_ok=True)

            # Generate thumbnail for the edited image
            edited_thumbnail_filename = None
            try:
                from utils.image_processing import generate_thumbnail, get_thumbnail_filename
                edited_thumb_basename = get_thumbnail_filename(edited_basename)
                edited_thumb_path = edited_path.parent / edited_thumb_basename

                success = generate_thumbnail(edited_path, edited_thumb_path)
                if success:
                    edited_thumbnail_filename = edited_thumb_basename
                    editing_logger.info(
                        "Generated edited image thumbnail: %s",
                        sanitize_log_value(edited_thumb_basename),
                    )
                else:
                    editing_logger.warning(
                        "Failed to generate thumbnail for edited image: %s",
                        sanitize_log_value(edited_basename),
                    )
            except Exception as e:
                editing_logger.error(
                    "Error generating thumbnail for edited image %s: %s",
                    sanitize_log_value(edited_basename),
                    sanitize_log_value(e),
                )

            if previous_thumbnail_filename and previous_thumbnail_filename != edited_thumbnail_filename:
                edited_path.with_name(previous_thumbnail_filename).unlink(missing_ok=True)

            # Update the database with the basename of the edited file and its thumbnail
            upload.edited_filename = edited_basename
            upload.edited_thumbnail_filename = edited_thumbnail_filename
            db.query(ImagePiiVerification).filter(
                ImagePiiVerification.image_uuid == str(upload.uuid),
                ImagePiiVerification.image_variant == "edited",
            ).delete(synchronize_session=False)
            try:
                from utils.image_metadata import extract_image_metadata, upsert_image_metadata
                metadata_result = extract_image_metadata(
                    image_bytes=image_bytes,
                    file_size_bytes=len(image_bytes),
                )
                upsert_image_metadata(
                    db,
                    image_uuid=str(upload.uuid),
                    image_variant="edited",
                    direct_image_upload_id=upload.id,
                    metadata=metadata_result,
                )
            except Exception as e:
                editing_logger.warning(
                    "Failed to store edited metadata for upload %s: %s",
                    sanitize_log_value(upload_id),
                    sanitize_log_value(e),
                )

            try:
                from utils.pii_verification import enqueue_pii_detection
                enqueue_pii_detection(
                    current_app._get_current_object(),
                    str(upload.uuid),
                    "edited",
                    str(edited_path),
                )
            except Exception as e:
                editing_logger.warning(
                    "Failed to enqueue PII detection for edited upload %s: %s",
                    sanitize_log_value(upload_id),
                    sanitize_log_value(e),
                )
            db.commit()
            bump_media_cache_version(str(upload.uuid))

            editing_logger.info(
                "Saved edited image for upload %s image_uuid %s by user %s",
                sanitize_log_value(upload_id),
                sanitize_log_value(upload.uuid),
                sanitize_log_value(current_user.id),
            )
            if has_non_pending and override_allowed:
                _log_sensitive_operation(
                    operation="direct_upload_anonymize_override",
                    status="completed",
                    details={
                        "upload_id": upload.id,
                        "upload_uuid": str(upload.uuid),
                        "task_states": task_states,
                        "source": "anonymize_ui",
                    },
                )
            return jsonify({"message": "Image saved successfully."}, 200)

        except Exception as e:
            db.rollback()
            editing_logger.error(
                "Error saving edited image for upload %s: %s",
                sanitize_log_value(upload_id),
                sanitize_log_value(traceback.format_exc()),
            )
            return jsonify({"error": "An error occurred while saving the image."}), 500
