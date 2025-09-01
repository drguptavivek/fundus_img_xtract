# direct_uploads/edit_upload.py

from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import bp
from .utils import with_session
from auth.roles import roles_required
from models import DirectImageUpload, Hospital, LabUnit, Camera, Disease, Area, User


def _to_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


@bp.route("/direct/upload/edit/<int:upload_id>", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def edit_upload(upload_id):
    with with_session() as db:
        upload = db.get(DirectImageUpload, upload_id)
        if not upload:
            flash("Upload not found.", "danger")
            return redirect(url_for("direct_uploads.dashboard"))

        is_admin = current_user.has_role('admin')
        is_manager = current_user.has_role('data_manager')
        can_choose_any = is_admin or is_manager

        # can edit if admin/manager OR owner
        if not (can_choose_any or upload.uploader_id == current_user.id):
            flash("You don't have permission to edit this upload.", "danger")
            return redirect(url_for("direct_uploads.dashboard"))

        # Build allowed sets ONLY for contributors (non-admin, non-manager)
        allowed_lab_unit_ids = set()
        allowed_hospital_ids = set()
        if not can_choose_any:
            user_db = db.execute(
                select(User).options(selectinload(User.lab_units))
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

            # RBAC: contributors must stay within their own assignments
            if not can_choose_any:
                if lid not in allowed_lab_unit_ids or hid not in allowed_hospital_ids:
                    flash("You cannot assign this hospital or lab unit.", "danger")
                    return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id), code=303)

            # Validate entities
            hospital = db.get(Hospital, hid)
            lab_unit = db.get(LabUnit, lid)
            camera   = db.get(Camera, cid)
            disease  = db.get(Disease, did)
            area     = db.get(Area, aid)

            if not all([hospital, lab_unit, camera, disease, area]):
                flash("Invalid selection for one or more fields.", "danger")
                return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id), code=303)

            # Consistency: lab unit must belong to selected hospital
            if lab_unit.hospital_id != hospital.id:
                flash("Selected Lab Unit does not belong to the selected Hospital.", "danger")
                return redirect(url_for("direct_uploads.edit_upload", upload_id=upload_id), code=303)

            # Apply updates
            upload.hospital_id = hospital.id
            upload.lab_unit_id = lab_unit.id
            upload.camera_id   = camera.id
            upload.disease_id  = disease.id
            upload.area_id     = area.id
            upload.is_mydriatic = is_mydriatic

            db.commit()
            current_app.logger.info(
                "Upload %s metadata edited by %s (%s)",
                upload.id, current_user.username, current_user.id
            )
            flash("Upload metadata updated successfully.", "success")
            return redirect(url_for("direct_uploads.dashboard"), code=303)

        # GET options: admins/managers see all; contributors see only their own
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

        cameras   = db.scalars(select(Camera).order_by(Camera.name)).all()
        diseases  = db.scalars(select(Disease).order_by(Disease.name)).all()
        areas     = db.scalars(select(Area).order_by(Area.name)).all()

        return render_template(
            "direct_uploads/edit_upload.html",
            upload=upload,
            hospitals=hospitals, lab_units=lab_units,
            cameras=cameras, diseases=diseases, areas=areas
        )
