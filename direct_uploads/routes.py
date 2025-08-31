from flask import jsonify, request, render_template, redirect, url_for, flash, current_app, session
from flask_login import current_user, login_required
from . import bp
from models import User, LabUnit, Hospital, Session, DIRECT_UPLOAD_DIR, DirectImageUpload, Camera, Disease, Area
from auth.roles import roles_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime
import os
import hashlib
from werkzeug.utils import secure_filename

@bp.route("/direct/upload", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def upload():
    db_session = Session()
    try:
        if request.method == "POST":
            hospital_id = request.form.get("hospital_id")
            lab_unit_id = request.form.get("lab_unit_id")
            camera_id = request.form.get("camera_id")
            disease_id = request.form.get("disease_id")
            area_id = request.form.get("area_id")
            is_mydriatic = request.form.get("is_mydriatic") == "on"
            files = request.files.getlist("files")

            # Basic validation
            if not all([hospital_id, lab_unit_id, camera_id, disease_id, area_id]):
                flash("All fields are required.", "danger")
                return redirect(url_for("direct_uploads.upload"))

            hospital = db_session.get(Hospital, hospital_id)
            lab_unit = db_session.get(LabUnit, lab_unit_id)
            camera = db_session.get(Camera, camera_id)
            disease = db_session.get(Disease, disease_id)
            area = db_session.get(Area, area_id)

            if not all([hospital, lab_unit, camera, disease, area]):
                flash("Invalid selection for one or more fields.", "danger")
                return redirect(url_for("direct_uploads.upload"))

            uploaded_count = 0
            failed_uploads = []
            
            today_str = datetime.now().strftime("%Y_%m_%d")
            upload_dir = DIRECT_UPLOAD_DIR / today_str
            upload_dir.mkdir(parents=True, exist_ok=True)

            dup_user_id_dir = upload_dir / f"dup_{current_user.id}"
            dup_user_id_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                if file.filename == '':
                    failed_uploads.append({"filename": "N/A", "reason": "No selected file"})
                    continue

                filename = secure_filename(file.filename)
                file_content = file.read()
                md5_hash = hashlib.md5(file_content).hexdigest()

                # Check for duplicates
                existing_file = db_session.execute(
                    select(DirectImageUpload).filter_by(file_hash=md5_hash)
                ).scalar_one_or_none()

                if existing_file:
                    # Save duplicate to a specific subdirectory
                    file_path = dup_user_id_dir / filename
                    with open(file_path, "wb") as f:
                        f.write(file_content)
                    failed_uploads.append({"filename": filename, "reason": "Duplicate file"})
                    continue

                # Check user upload quota
                if current_user.file_upload_count >= current_app.config.get("MAX_FILES_PER_UPLOAD", 50):
                    failed_uploads.append({"filename": filename, "reason": "Upload quota exceeded"})
                    continue

                # Save the file
                file_path = upload_dir / filename
                with open(file_path, "wb") as f:
                    f.write(file_content)

                # Save metadata to DB
                direct_upload = DirectImageUpload(
                    filename=filename,
                    filepath=str(file_path),
                    file_hash=md5_hash,
                    uploader_id=current_user.id,
                    hospital_id=hospital.id,
                    lab_unit_id=lab_unit.id,
                    camera_id=camera.id,
                    disease_id=disease.id,
                    area_id=area.id,
                    is_mydriatic=is_mydriatic,
                )
                db_session.add(direct_upload)
                current_user.file_upload_count += 1
                uploaded_count += 1
            
            db_session.commit()
            flash(f"Successfully uploaded {uploaded_count} files.", "success")
            if failed_uploads:
                flash(f"Failed to upload {len(failed_uploads)} files.", "warning")
            
            session["upload_results"] = {
                "uploaded_count": uploaded_count,
                "failed_count": len(failed_uploads),
                "failed_uploads": failed_uploads
            }
            return redirect(url_for("direct_uploads.upload_status"))

        # GET request
        hospitals = db_session.execute(select(Hospital).order_by(Hospital.id)).scalars().all()
        lab_units = db_session.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.id)).scalars().all()
        cameras = db_session.execute(select(Camera).order_by(Camera.id)).scalars().all()
        diseases = db_session.execute(select(Disease).order_by(Disease.id)).scalars().all()
        areas = db_session.execute(select(Area).order_by(Area.id)).scalars().all()

        return render_template(
            "direct_uploads/upload.html",
            hospitals=hospitals,
            lab_units=lab_units,
            cameras=cameras,
            diseases=diseases,
            areas=areas
        )
    except Exception as e:
        db_session.rollback()
        current_app.logger.exception("Direct upload error: %s", e)
        flash("An unexpected error occurred during upload.", "danger")
        return redirect(url_for("direct_uploads.upload"))
    finally:
        db_session.close()

@bp.route("/direct/upload/status", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
def upload_status():
    results = session.pop("upload_results", {
        "uploaded_count": 0,
        "failed_count": 0,
        "failed_uploads": []
    })
    return render_template("direct_uploads/upload_status.html", results=results)


@bp.route("/direct/list", methods=["GET"])
@roles_required('data_manager', 'admin')
def list_uploads():
    # TODO: Implement list of direct uploads
    return "List of direct uploads"

@bp.route("/api/lab-units/<int:user_id>", methods=["GET"])
@login_required
def get_lab_units(user_id):
    db_session = Session()
    user = db_session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Security check: only admin/data_manager can query for other users
    if not current_user.has_role('admin', 'data_manager') and current_user.id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    lab_units = [{"id": lu.id, "name": lu.name} for lu in user.lab_units]
    db_session.close()
    return jsonify(lab_units)

@bp.route("/api/hospital/<int:lab_unit_id>", methods=["GET"])
@login_required
def get_hospital(lab_unit_id):
    db_session = Session()
    lab_unit = db_session.get(LabUnit, lab_unit_id)
    if not lab_unit:
        db_session.close()
        return jsonify({"error": "Lab unit not found"}), 404
    
    hospital = {"id": lab_unit.hospital.id, "name": lab_unit.hospital.name}
    db_session.close()
    return jsonify(hospital)
