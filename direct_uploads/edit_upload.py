from flask import request, render_template, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import select
from . import bp
from .utils import with_session
from auth.roles import roles_required
from models import DirectImageUpload, Hospital, LabUnit, Camera, Disease, Area

@bp.route("/direct/upload/edit/<int:upload_id>", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def edit_upload(upload_id):
    with with_session() as db:
        upload = db.get(DirectImageUpload, upload_id)
        if not upload:
            flash("Upload not found.", "danger")
            return redirect(url_for("direct_uploads.dashboard"))

        if not (current_user.has_role('admin', 'data_manager') or upload.uploader_id == current_user.id):
            flash("You don't have permission to edit this upload.", "danger")
            return redirect(url_for("direct_uploads.dashboard"))

        if request.method == "POST":
            req = request.form
            if not all([req.get("hospital_id"), req.get("lab_unit_id"), req.get("camera_id"), req.get("disease_id"), req.get("area_id")]):
                flash("All fields are required.", "danger")
                return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id))

            upload.hospital_id = int(req.get("hospital_id"))
            upload.lab_unit_id = int(req.get("lab_unit_id"))
            upload.camera_id   = int(req.get("camera_id"))
            upload.disease_id  = int(req.get("disease_id"))
            upload.area_id     = int(req.get("area_id"))
            upload.is_mydriatic = req.get("is_mydriatic") == "on"

            db.commit()
            flash("Upload metadata updated successfully.", "success")
            return redirect(url_for("direct_uploads.dashboard"))

        hospitals = db.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        lab_units = db.execute(select(LabUnit).order_by(LabUnit.name)).scalars().all()
        cameras   = db.execute(select(Camera).order_by(Camera.name)).scalars().all()
        diseases  = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        areas     = db.execute(select(Area).order_by(Area.name)).scalars().all()

        return render_template("direct_uploads/edit_upload.html",
                               upload=upload, hospitals=hospitals, lab_units=lab_units,
                               cameras=cameras, diseases=diseases, areas=areas)
