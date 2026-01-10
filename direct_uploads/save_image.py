import base64, traceback
import logging
from pathlib import Path
from flask import request, jsonify, current_app
from flask_login import current_user
from sqlalchemy import select
from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from models import DirectImageUpload, BASE_DIR, GradingTask
from utils.fileUtils import abs_from_parts
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.log_sanitize import sanitize_log_value


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
            if any(_normalize_task_state(state) not in ("", "pending") for state in task_states):
                editing_logger.warning(
                    "Save blocked for upload %s due to task states %s",
                    sanitize_log_value(upload_id),
                    sanitize_log_value(task_states),
                )
                return jsonify({"error": "Cannot edit image while grading tasks are in progress."}), 409

            image_data = request.get_json().get('image_data') if request.is_json else request.form.get('image_data')
            if not image_data:
                editing_logger.warning(
                    "No image data for upload %s",
                    sanitize_log_value(upload_id),
                )
                return jsonify({"error": "No image data provided."}), 400

            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]

            try:
                image_bytes = base64.b64decode(image_data)
            except Exception as e:
                editing_logger.error(
                    "Base64 decode error for upload %s: %s",
                    sanitize_log_value(upload_id),
                    sanitize_log_value(e),
                )
                return jsonify({"error": "Invalid image data provided."}), 400

            # Correctly determine the path for the new edited file
            edited_basename = f"edited_{upload.filename}"
            edited_path = abs_from_parts(upload.folder_rel, edited_basename, kind="edited")
            
            # Ensure the destination directory exists
            edited_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the new edited image
            edited_path.write_bytes(image_bytes)

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

            # Update the database with the basename of the edited file and its thumbnail
            upload.edited_filename = edited_basename
            upload.edited_thumbnail_filename = edited_thumbnail_filename
            db.commit()

            editing_logger.info(
                "Saved edited image for upload %s by user %s",
                sanitize_log_value(upload_id),
                sanitize_log_value(current_user.id),
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
