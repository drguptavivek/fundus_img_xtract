from flask import jsonify, request, render_template, redirect, url_for, flash, current_app, session
from flask_login import current_user, login_required
from . import bp
from models import User, LabUnit, Hospital, Session, DIRECT_UPLOAD_DIR, DirectImageUpload, Camera, Disease, Area, Job, JobItem, BASE_DIR
from auth.roles import roles_required
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime
import os
import hashlib
from werkzeug.utils import secure_filename
import magic # For content sniffing
import uuid
import json


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

            current_app.logger.info("Direct upload initiated by user %s (ID: %s) from IP %s", 
                                  current_user.username, current_user.id, request.remote_addr)
            current_app.logger.info("Upload parameters - Hospital: %s, Lab Unit: %s, Camera: %s, Disease: %s, Area: %s, Mydriatic: %s", 
                                  hospital_id, lab_unit_id, camera_id, disease_id, area_id, is_mydriatic)

            # Configuration for file limits and allowed types
            MAX_FILES_ALLOWED = int(os.getenv("DIRECT_UPLOAD_MAX_FILES", 100))
            MAX_FILE_SIZE_MB = int(os.getenv("DIRECT_UPLOAD_MAX_FILE_SIZE_MB", 5))
            MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
            ALLOWED_MIMETYPES = os.getenv("DIRECT_UPLOAD_ALLOWED_MIMETYPES", "image/jpeg,image/png").split(",")

            # Basic validation
            if not all([hospital_id, lab_unit_id, camera_id, disease_id, area_id]):
                current_app.logger.warning("Direct upload failed: Missing required fields for user %s (ID: %s)", 
                                         current_user.username, current_user.id)
                flash("All fields are required.", "danger")
                return redirect(url_for("direct_uploads.upload"))

            hospital = db_session.get(Hospital, hospital_id)
            lab_unit = db_session.get(LabUnit, lab_unit_id)
            camera = db_session.get(Camera, camera_id)
            disease = db_session.get(Disease, disease_id)
            area = db_session.get(Area, area_id)

            if not all([hospital, lab_unit, camera, disease, area]):
                current_app.logger.warning("Direct upload failed: Invalid selection for one or more fields for user %s (ID: %s)", 
                                         current_user.username, current_user.id)
                flash("Invalid selection for one or more fields.", "danger")
                return redirect(url_for("direct_uploads.upload"))

            # Create a new Job for this upload session
            job_token = str(uuid.uuid4())
            new_job = Job(
                token=job_token,
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr
            )
            db_session.add(new_job)
            db_session.flush() # To get the job ID

            current_app.logger.info("Created new job %s for user %s (ID: %s)", 
                                  new_job.id, current_user.username, current_user.id)

            today_str = datetime.now().strftime("%Y_%m_%d")
            upload_dir = DIRECT_UPLOAD_DIR / today_str
            upload_dir.mkdir(parents=True, exist_ok=True)

            dup_user_id_dir = upload_dir / f"dup_{current_user.id}"
            dup_user_id_dir.mkdir(parents=True, exist_ok=True)

            job_items_data = []
            file_count = len(files)
            current_app.logger.info("Processing %s files for upload", file_count)

            for file in files:
                filename = secure_filename(file.filename)
                job_item_status = "queued"
                job_item_detail = ""

                if file.filename == '':
                    job_item_status = "error"
                    job_item_detail = "No selected file"
                    current_app.logger.warning("File upload error: No selected file")
                else:
                    file_content = file.read()
                    file_size = len(file_content)
                    current_app.logger.info("Processing file: %s, Size: %s bytes", filename, file_size)

                    # File size check
                    if file_size > MAX_FILE_SIZE_BYTES:
                        job_item_status = "error"
                        job_item_detail = f"File too large (max {MAX_FILE_SIZE_MB}MB)"
                        current_app.logger.warning("File upload error: File too large - %s bytes for file %s", file_size, filename)
                    else:
                        # Content sniffing and MIME type check
                        mime_type = magic.from_buffer(file_content, mime=True)
                        if mime_type not in ALLOWED_MIMETYPES:
                            job_item_status = "error"
                            job_item_detail = f"Invalid file type: {mime_type}. Only JPG, JPEG, PNG allowed."
                            current_app.logger.warning("File upload error: Invalid file type %s for file %s", mime_type, filename)
                        else:
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
                                job_item_status = "error"
                                job_item_detail = "Duplicate file"
                                current_app.logger.info("File upload: Duplicate detected for file %s", filename)
                            else:
                                # Check user upload quota
                                if current_user.file_upload_count >= current_app.config.get("MAX_FILES_PER_UPLOAD", 50):
                                    job_item_status = "error"
                                    job_item_detail = "Upload quota exceeded"
                                    current_app.logger.warning("File upload error: Upload quota exceeded for user %s (ID: %s)", 
                                                             current_user.username, current_user.id)
                                else:
                                    # Save the file
                                    file_path = upload_dir / filename
                                    with open(file_path, "wb") as f:
                                        f.write(file_content)

                                    # Save metadata to DB with relative path
                                    relative_path = str(file_path.relative_to(BASE_DIR))
                                    direct_upload = DirectImageUpload(
                                        filename=filename,
                                        filepath=relative_path,
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
                                    job_item_status = "completed"
                                    job_item_detail = "File uploaded successfully"
                                    current_app.logger.info("File uploaded successfully: %s", filename)
                
                job_items_data.append(JobItem(
                    job_id=new_job.id,
                    filename=filename,
                    state=job_item_status,
                    detail=job_item_detail,
                    uploader_user_id=current_user.id,
                    uploader_username=current_user.username,
                    uploader_ip=request.remote_addr
                ))
            
            db_session.add_all(job_items_data)
            new_job.status = "completed" if all(item.state == "completed" for item in job_items_data) else "error"
            db_session.commit()

            success_count = sum(1 for item in job_items_data if item.state == "completed")
            error_count = len(job_items_data) - success_count
            current_app.logger.info("Upload job %s completed. Success: %s, Errors: %s", 
                                  new_job.id, success_count, error_count)

            flash("Upload process initiated. Check status for details.", "info")
            return redirect(url_for("direct_uploads.upload_processing", job_id=new_job.id))

        # GET request
        current_app.logger.info("Direct upload page accessed by user %s (ID: %s)", 
                              current_user.username, current_user.id)
        
        # Filter lab units to only those associated with the current user
        user = db_session.get(User, current_user.id)  # attaches to this db_session
        user_lab_unit_ids = {lu.id for lu in user.lab_units}
        lab_units = db_session.execute(
            select(LabUnit)
            .where(LabUnit.id.in_(user_lab_unit_ids))
            .options(selectinload(LabUnit.hospital))
            .order_by(LabUnit.id)
        ).scalars().all()

        # Filter hospitals to only those associated with the current user's lab units
        accessible_hospital_ids = {lu.hospital_id for lu in lab_units}
        hospitals = db_session.execute(
            select(Hospital)
            .where(Hospital.id.in_(accessible_hospital_ids))
            .order_by(Hospital.name)
        ).scalars().all()

        cameras = db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        diseases = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
        areas = db_session.execute(select(Area).order_by(Area.name)).scalars().all()

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

@bp.route("/direct/upload/processing/<int:job_id>", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
def upload_processing(job_id):
    return render_template("direct_uploads/upload_processing.html", job_id=job_id)


@bp.route("/direct/dashboard", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def dashboard():
    db_session = Session()
    try:
        # Handle bulk operations POST request
        if request.method == "POST":
            selected_ids = request.form.getlist('selected_uploads')
            action = request.form.get('action')
            
            # Limit bulk operations to 30 files
            if len(selected_ids) > 30:
                flash("Maximum 30 files can be processed in a single operation.", "danger")
                return redirect(url_for("direct_uploads.dashboard"))
            
            if action == 'bulk_edit' and selected_ids:
                # Get the new values from the form
                new_hospital_id = request.form.get('new_hospital_id')
                new_lab_unit_id = request.form.get('new_lab_unit_id')
                new_camera_id = request.form.get('new_camera_id')
                new_disease_id = request.form.get('new_disease_id')
                new_area_id = request.form.get('new_area_id')
                new_is_mydriatic = request.form.get('new_is_mydriatic')
                
                # Build the update query
                update_query = select(DirectImageUpload).where(DirectImageUpload.id.in_([int(id) for id in selected_ids]))
                
                # If user is not admin or data_manager, filter by uploader_id
                if not current_user.has_role('admin', 'data_manager'):
                    update_query = update_query.where(DirectImageUpload.uploader_id == current_user.id)
                
                # Get the uploads to update
                uploads_to_update = db_session.execute(update_query).scalars().all()
                
                # Update the selected fields
                updated_count = 0
                for upload in uploads_to_update:
                    if new_hospital_id:
                        upload.hospital_id = int(new_hospital_id)
                    if new_lab_unit_id:
                        upload.lab_unit_id = int(new_lab_unit_id)
                    if new_camera_id:
                        upload.camera_id = int(new_camera_id)
                    if new_disease_id:
                        upload.disease_id = int(new_disease_id)
                    if new_area_id:
                        upload.area_id = int(new_area_id)
                    if new_is_mydriatic is not None:
                        upload.is_mydriatic = new_is_mydriatic == 'on'
                    updated_count += 1
                
                db_session.commit()
                flash(f"Successfully updated {updated_count} uploads.", "success")
                
            elif action == 'bulk_delete' and selected_ids:
                # Build the delete query
                delete_query = select(DirectImageUpload).where(DirectImageUpload.id.in_([int(id) for id in selected_ids]))
                
                # If user is not admin or data_manager, filter by uploader_id
                if not current_user.has_role('admin', 'data_manager'):
                    delete_query = delete_query.where(DirectImageUpload.uploader_id == current_user.id)
                
                # Get the uploads to delete
                uploads_to_delete = db_session.execute(delete_query).scalars().all()
                
                # Delete the selected uploads
                deleted_count = 0
                for upload in uploads_to_delete:
                    # Delete the file from disk using absolute path
                    try:
                        absolute_path = upload.absolute_filepath
                        if os.path.exists(absolute_path):
                            os.remove(absolute_path)
                    except Exception as e:
                        current_app.logger.warning("Failed to delete file %s: %s", upload.absolute_filepath, e)
                    
                    # Delete from database
                    db_session.delete(upload)
                    deleted_count += 1
                
                db_session.commit()
                flash(f"Successfully deleted {deleted_count} uploads.", "success")
            else:
                flash("No uploads selected for operation.", "warning")
            
            # Redirect to the same page to show updated data
            return redirect(url_for("direct_uploads.dashboard"))
        
        # GET request - show dashboard
        # Get page number from request, default to 1
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        # Validate page number
        if page < 1:
            page = 1
            
        # Build base query for filtering
        base_query = select(DirectImageUpload)
        
        # If user is not admin or data_manager, filter by uploader_id
        if not current_user.has_role('admin', 'data_manager'):
            base_query = base_query.where(DirectImageUpload.uploader_id == current_user.id)
            
        # Get total count for pagination
        count_query = select(func.count()).select_from(base_query.subquery())
        total_count = db_session.execute(count_query).scalar_one()
        
        # Calculate total pages
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        
        # Validate page number against total pages
        if page > total_pages:
            page = total_pages if total_pages > 0 else 1
        
        # Build the main query with ordering and pagination
        main_query = base_query.order_by(DirectImageUpload.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        
        # Apply pagination
        uploads = db_session.execute(main_query).scalars().all()
        
        # Get related objects for display
        hospital_ids = {upload.hospital_id for upload in uploads}
        lab_unit_ids = {upload.lab_unit_id for upload in uploads}
        camera_ids = {upload.camera_id for upload in uploads}
        disease_ids = {upload.disease_id for upload in uploads}
        area_ids = {upload.area_id for upload in uploads}
        user_ids = {upload.uploader_id for upload in uploads}
        
        # Fetch related data
        hospitals = {h.id: h for h in db_session.execute(
            select(Hospital).where(Hospital.id.in_(hospital_ids))
        ).scalars().all()} if hospital_ids else {}
        
        lab_units = {lu.id: lu for lu in db_session.execute(
            select(LabUnit).where(LabUnit.id.in_(lab_unit_ids))
        ).scalars().all()} if lab_unit_ids else {}
        
        cameras = {c.id: c for c in db_session.execute(
            select(Camera).where(Camera.id.in_(camera_ids))
        ).scalars().all()} if camera_ids else {}
        
        diseases = {d.id: d for d in db_session.execute(
            select(Disease).where(Disease.id.in_(disease_ids))
        ).scalars().all()} if disease_ids else {}
        
        areas = {a.id: a for a in db_session.execute(
            select(Area).where(Area.id.in_(area_ids))
        ).scalars().all()} if area_ids else {}
        
        users = {u.id: u for u in db_session.execute(
            select(User).where(User.id.in_(user_ids))
        ).scalars().all()} if user_ids else {}
        
        # Get all available options for bulk edit dropdowns
        all_hospitals = db_session.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        all_lab_units = db_session.execute(select(LabUnit).order_by(LabUnit.name)).scalars().all()
        all_cameras = db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        all_diseases = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
        all_areas = db_session.execute(select(Area).order_by(Area.name)).scalars().all()
        
        # KPI Data - Total uploads
        kpi_total_uploads = total_count
        
        # KPI Data - Uploads by camera type
        camera_kpis = {}
        # Build camera KPI query with proper filtering
        camera_kpi_query = select(Camera.name, func.count(DirectImageUpload.id).label('count')) \
            .join(DirectImageUpload, DirectImageUpload.camera_id == Camera.id) \
            .group_by(Camera.name)
        
        # Apply user filter if needed
        if not current_user.has_role('admin', 'data_manager'):
            camera_kpi_query = camera_kpi_query.where(DirectImageUpload.uploader_id == current_user.id)
            
        camera_kpi_results = db_session.execute(camera_kpi_query).all()
        for cam_name, count in camera_kpi_results:
            camera_kpis[cam_name] = count
        
        # KPI Data - Uploads by disease
        disease_kpis = {}
        # Build disease KPI query with proper filtering
        disease_kpi_query = select(Disease.name, func.count(DirectImageUpload.id).label('count')) \
            .join(DirectImageUpload, DirectImageUpload.disease_id == Disease.id) \
            .group_by(Disease.name)
        
        # Apply user filter if needed
        if not current_user.has_role('admin', 'data_manager'):
            disease_kpi_query = disease_kpi_query.where(DirectImageUpload.uploader_id == current_user.id)
            
        disease_kpi_results = db_session.execute(disease_kpi_query).all()
        for dis_name, count in disease_kpi_results:
            disease_kpis[dis_name] = count
        
        # KPI Data - Uploads by area
        area_kpis = {}
        # Build area KPI query with proper filtering
        area_kpi_query = select(Area.name, func.count(DirectImageUpload.id).label('count')) \
            .join(DirectImageUpload, DirectImageUpload.area_id == Area.id) \
            .group_by(Area.name)
        
        # Apply user filter if needed
        if not current_user.has_role('admin', 'data_manager'):
            area_kpi_query = area_kpi_query.where(DirectImageUpload.uploader_id == current_user.id)
            
        area_kpi_results = db_session.execute(area_kpi_query).all()
        for ar_name, count in area_kpi_results:
            area_kpis[ar_name] = count
        
        current_app.logger.info("Direct upload dashboard accessed by user %s (ID: %s). Page: %s, Total uploads: %s", 
                              current_user.username, current_user.id, page, total_count)
        
        return render_template(
            "direct_uploads/dashboard.html",
            uploads=uploads,
            hospitals=hospitals,
            lab_units=lab_units,
            cameras=cameras,
            diseases=diseases,
            areas=areas,
            users=users,
            all_hospitals=all_hospitals,
            all_lab_units=all_lab_units,
            all_cameras=all_cameras,
            all_diseases=all_diseases,
            all_areas=all_areas,
            current_page=page,
            total_pages=total_pages,
            total_count=total_count,
            per_page=per_page,
            kpi_total_uploads=kpi_total_uploads,
            camera_kpis=camera_kpis,
            disease_kpis=disease_kpis,
            area_kpis=area_kpis
        )
    except Exception as e:
        db_session.rollback()
        current_app.logger.exception("Error in direct upload dashboard: %s", e)
        flash("An error occurred while loading the dashboard.", "danger")
        return redirect(url_for("direct_uploads.upload"))
    finally:
        db_session.close()


@bp.route("/direct/upload/results/<int:job_id>", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
def upload_results(job_id):
    db_session = Session()
    try:
        job = db_session.get(Job, job_id)
        if not job or job.uploader_user_id != current_user.id:
            flash("Upload job not found or unauthorized access.", "danger")
            return redirect(url_for("direct_uploads.upload"))
        
        job_items = db_session.execute(
            select(JobItem)
            .where(JobItem.job_id == job_id)
            .order_by(JobItem.id)
        ).scalars().all()

        uploaded_count = sum(1 for item in job_items if item.state == "completed")
        failed_count = len(job_items) - uploaded_count
        failed_uploads = [{"filename": item.filename, "reason": item.detail} for item in job_items if item.state == "error"]

        results = {
            "uploaded_count": uploaded_count,
            "failed_count": failed_count,
            "failed_uploads": failed_uploads
        }
        return render_template("direct_uploads/upload_results.html", results=results, job=job)
    finally:
        db_session.close()


@bp.route("/api/direct/upload/status/<int:job_id>", methods=["GET"])
@login_required
def api_upload_status(job_id):
    db_session = Session()
    try:
        job = db_session.get(Job, job_id)
        if not job or job.uploader_user_id != current_user.id:
            return jsonify({"error": "Upload job not found or unauthorized access."}), 404
        
        job_items = db_session.execute(
            select(JobItem)
            .where(JobItem.job_id == job_id)
            .order_by(JobItem.id)
        ).scalars().all()

        items = [
            {
                "filename": item.filename,
                "state": item.state,
                "detail": item.detail
            }
            for item in job_items
        ]

        return jsonify({
            "job_id": job_id,
            "job_status": job.status,
            "items": items
        })
    finally:
        db_session.close()


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
