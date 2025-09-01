import base64, traceback
from pathlib import Path
from flask import request, jsonify, current_app
from flask_login import current_user
from . import bp
from .utils import with_session
from auth.roles import roles_required
from models import DirectImageUpload, BASE_DIR
from .paths import abs_from_parts

@bp.route("/direct/upload/save_image/<int:upload_id>", methods=["POST"])
@roles_required('contributor', 'data_manager', 'admin')
def save_edited_image(upload_id: int):
    with with_session() as db:
        try:
            current_app.logger.info("Save image request for upload_id=%s", upload_id)
            current_app.logger.info("Content-Type: %s", request.content_type)

            upload = db.get(DirectImageUpload, upload_id)
            if not upload:
                current_app.logger.warning("Upload not found for id: %s", upload_id)
                return jsonify({"error": "Upload not found."}), 404

            if not (current_user.has_role('admin', 'data_manager') or upload.uploader_id == current_user.id):
                current_app.logger.warning("User %s lacks permission to edit %s", current_user.id, upload_id)
                return jsonify({"error": "You don't have permission to edit this upload."}, 403)

            image_data = request.get_json().get('image_data') if request.is_json else request.form.get('image_data')
            if not image_data:
                current_app.logger.warning("No image data for upload %s", upload_id)
                return jsonify({"error": "No image data provided."}, 400)

            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]

            try:
                image_bytes = base64.b64decode(image_data)
            except Exception as e:
                current_app.logger.error("Base64 decode error for upload %s: %s", upload_id, e)
                return jsonify({"error": "Invalid image data provided."}, 400)

            # Correctly determine the path for the new edited file
            edited_basename = f"edited_{upload.filename}"
            edited_path = abs_from_parts(upload.folder_rel, edited_basename, kind="edited")
            
            # Ensure the destination directory exists
            edited_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the new edited image
            edited_path.write_bytes(image_bytes)

            # Update the database with the basename of the edited file
            upload.edited_filename = edited_basename
            db.commit()

            current_app.logger.info("Saved edited image for upload %s by user %s", upload_id, current_user.id)
            return jsonify({"message": "Image saved successfully."}, 200)

        except Exception as e:
            db.rollback()
            current_app.logger.error("Error saving edited image for upload %s:\n%s",
                                     upload_id, traceback.format_exc())
            return jsonify({"error": "An error occurred while saving the image."}, 500)
