import traceback
from flask import render_template, redirect, url_for, flash, current_app, url_for as flask_url_for
from flask_login import current_user
from werkzeug.exceptions import NotFound
from . import bp
from .utils import with_session, require_owner_or_roles
from auth.roles import roles_required
from models import DirectImageUpload, Hospital, LabUnit, Camera, Disease, Area, User

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

            display_path_orig = upload.filepath
            display_path_edited = upload.edited_image_path or None

            image_url = flask_url_for("media.serve_direct_upload", filepath=display_path_orig)
            print(image_url)
            current_app.logger.info("Edit image %s using '%s'", upload_id, display_path_orig)

            hospital = db.get(Hospital, upload.hospital_id)
            lab_unit = db.get(LabUnit, upload.lab_unit_id)
            camera   = db.get(Camera, upload.camera_id)
            disease  = db.get(Disease, upload.disease_id)
            area     = db.get(Area, upload.area_id)
            uploader = db.get(User, upload.uploader_id)

            return render_template("direct_uploads/edit_image.html",
                                   upload=upload, hospital=hospital, lab_unit=lab_unit,
                                   camera=camera, disease=disease, area=area,
                                   uploader=uploader, image_url=image_url)
        except FileNotFoundError as e:
            current_app.logger.error("Missing file for upload_id=%s at %s", upload_id, e)
            flash("Image file not found on server.", "danger")
            return redirect(flask_url_for("direct_uploads.dashboard"))
        except Exception:
            current_app.logger.error("Error loading image editor for upload %s:\n%s",
                                     upload_id, traceback.format_exc())
            flash("An error occurred while loading the image editor.", "danger")
            return redirect(flask_url_for("direct_uploads.dashboard"))
