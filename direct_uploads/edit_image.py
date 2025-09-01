import traceback
from pathlib import Path
from flask import render_template, redirect, url_for, flash, current_app, url_for as flask_url_for, jsonify
from flask_login import current_user
from werkzeug.exceptions import NotFound
from . import bp
from .utils import with_session, require_owner_or_roles
from auth.roles import roles_required
from models import DirectImageUpload, Hospital, LabUnit, Camera, Disease, Area, User
from .paths import abs_from_parts

@bp.route("/direct/upload/edit_image/<int:upload_id>", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
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

            has_edited_version = bool(upload.edited_filename)
            if has_edited_version:
                image_url = flask_url_for("media.serve_img_edited", upload_id=upload.id)
                current_app.logger.info("Loading EDITED image %s for editing", upload_id)
            else:
                image_url = flask_url_for("media.serve_img_orig", upload_id=upload.id)
                current_app.logger.info("Loading ORIGINAL image %s for editing", upload_id)

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
            current_app.logger.error("Missing file for upload_id=%s at %s", upload_id, e)
            flash("Image file not found on server.", "danger")
            return redirect(flask_url_for("direct_uploads.dashboard"))
        except Exception:
            current_app.logger.error("Error loading image editor for upload %s:\n%s",
                                     upload_id, traceback.format_exc())
            flash("An error occurred while loading the image editor.", "danger")
            return redirect(flask_url_for("direct_uploads.dashboard"))

@bp.route("/direct/upload/restore_original/<int:upload_id>", methods=["POST"])
@roles_required('contributor', 'data_manager', 'admin')
def restore_original(upload_id: int):
    with with_session() as db:
        try:
            upload = db.get(DirectImageUpload, upload_id)
            if not upload:
                return jsonify({"error": "Upload not found."}), 404

            if not require_owner_or_roles(upload, 'admin', 'data_manager'):
                return jsonify({"error": "Permission denied."}), 403

            if not upload.edited_filename:
                return jsonify({"message": "No edited version to restore."}), 200

            # Delete the edited file
            edited_path = abs_from_parts(upload.folder_rel, upload.edited_filename, kind="edited")
            try:
                edited_path.unlink()
                current_app.logger.info("Deleted edited file: %s", edited_path)
            except FileNotFoundError:
                current_app.logger.warning("Edited file not found at %s, but proceeding to clear from DB.", edited_path)
            
            # Update the database
            upload.edited_filename = None
            db.commit()

            flash("Original image has been restored.", "success")
            return jsonify({"message": "Original image restored.", "redirect_url": flask_url_for('direct_uploads.edit_image', upload_id=upload_id)}), 200

        except Exception as e:
            db.rollback()
            current_app.logger.error("Error restoring original for upload %s:\n%s",
                                     upload_id, traceback.format_exc())
            return jsonify({"error": "An unexpected error occurred."}), 500

