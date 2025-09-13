from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func
import random
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User


@roles_required("admin", "optometrist", "ophthalmologist")
def index():
    if request.method == "POST":
        img_uuid = (request.form.get("image_uuid") or "").strip()
        code_for = (request.form.get("code_for") or request.form.get("gfor") or "glaucoma").strip().lower()
        if code_for not in {"glaucoma","dr","amd"}:
            code_for = "glaucoma"
        if img_uuid:
            # Validate UUID points to an image we can grade; add clear messaging for scenarios
            db = Session()
            try:
                # First check if it's an EncounterFile UUID
                ef = db.query(EncounterFile).filter(EncounterFile.uuid == img_uuid).first()
                diu = None
                if not ef:
                    # If not found, check if it's a DirectImageUpload UUID
                    diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == img_uuid).first()
                
                if not ef and not diu:
                    flash("No image found for that UUID.", "danger")
                    return redirect(url_for('grading.index'))
                
                # Basic image check by type or extension for EncounterFile
                if ef:
                    ext = ef.filename.rsplit('.', 1)[-1].lower() if ef.filename and '.' in ef.filename else ''
                    if not ((ef.file_type or '').lower().startswith('image') or ext in {"png","jpg","jpeg","gif","bmp","webp"}):
                        flash("That UUID does not reference an image.", "danger")
                        return redirect(url_for('grading.index'))
                
                # For DirectImageUpload, we assume it's always an image
                
                # Message depending on whether the current user already graded it for the selected type
                my_id = getattr(current_user, 'id', None)
                has_my = False
                if ef:
                    has_my = (
                        db.query(ImageGrading)
                          .filter(ImageGrading.encounter_file_id == ef.id,
                                  ImageGrading.graded_for == code_for,
                                  ImageGrading.grader_user_id == my_id)
                          .count()
                    )
                elif diu:
                    has_my = (
                        db.query(ImageGrading)
                          .filter(ImageGrading.direct_image_upload_id == diu.id,
                                  ImageGrading.graded_for == code_for,
                                  ImageGrading.grader_user_id == my_id)
                          .count()
                    )
                
                if code_for == 'amd':
                    flash("AMD grading is not available yet.", "warning")
                    return redirect(url_for('grading.index'))
                if has_my:
                    flash(f"Opening your previous {code_for.upper()} grading to revise.", "info")
                else:
                    flash(f"Opening image — no {code_for.upper()} grading by you yet.", "success")
            finally:
                db.close()

            # Redirect to appropriate endpoint based on image type
            if ef:
                if code_for == 'glaucoma':
                    return redirect(url_for('grading.remedio_glaucoma_image', uuid=img_uuid))
                elif code_for == 'dr':
                    return redirect(url_for('grading.remedio_dr_image', uuid=img_uuid))
            elif diu:
                # For direct images, check if it's a supported disease
                db = Session()
                try:
                    disease = db.query(Disease).filter(Disease.id == diu.disease_id).first()
                    if not disease:
                        flash("Disease not found for this direct image.", "danger")
                        return redirect(url_for('grading.index'))
                    
                    disease_name_lower = disease.name.lower()
                    if code_for == 'glaucoma' and disease_name_lower == 'glaucoma':
                        return redirect(url_for('grading.direct_image', uuid=img_uuid))
                    elif code_for == 'dr' and disease_name_lower == 'diabetic retinopathy':
                        # For DR direct images, we'll use the disease-based route
                        return redirect(url_for('grading.direct_disease_image', uuid=img_uuid, disease_id=diu.disease_id))
                    elif code_for == disease_name_lower:
                        # For other diseases, use the disease-based route
                        return redirect(url_for('grading.direct_disease_image', uuid=img_uuid, disease_id=diu.disease_id))
                    else:
                        # If the requested grading type doesn't match the image's disease
                        flash(f"This image is for {disease.name}, not {code_for.upper()}.", "warning")
                        return redirect(url_for('grading.index'))
                finally:
                    db.close()
        flash("Please enter a valid Image UUID", "warning")

    # Stats + most recent encounter with an ungraded glaucoma image
    db = Session()
    try:
        # Get impression counts for display
        type_rows = (
            db.query(ImageGrading.impression, func.count(ImageGrading.id))
              .group_by(ImageGrading.impression)
              .all()
        )
        type_counts = {k or 'Unknown': int(v) for k, v in type_rows}

        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 20
        # Filter my gradings by grading type and task type if provided
        gfor = (request.args.get('gfor') or 'all').strip().lower()
        task_type = (request.args.get('task_type') or 'all').strip().lower()
        my_q = (
            db.query(ImageGrading)
              .options(
                  joinedload(ImageGrading.image),
                  joinedload(ImageGrading.direct_image)
              )
              .filter(ImageGrading.grader_user_id == getattr(current_user, 'id', None))
              .order_by(ImageGrading.updated_at.desc())
        )
        if gfor and gfor != 'all':
            my_q = my_q.filter(ImageGrading.graded_for == gfor)
        if task_type and task_type != 'all':
            # Filter by task type (dual grading tasks vs direct gradings)
            if task_type == 'dual':
                # Only show gradings that are part of a dual grading task
                my_q = my_q.filter(ImageGrading.task_id.isnot(None))
            elif task_type == 'single':
                # Only show gradings that are NOT part of a dual grading task
                my_q = my_q.filter(ImageGrading.task_id.is_(None))
        total_mine = my_q.count()
        items_mine = (
            my_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        total_pages_mine = max(1, (total_mine + per_page - 1) // per_page) if total_mine else 1
        mine_prev_url = url_for('grading.index', p=page-1, gfor=gfor, task_type=task_type) if page > 1 else None
        mine_next_url = url_for('grading.index', p=page+1, gfor=gfor, task_type=task_type) if page < total_pages_mine else None
        
        # Get dual grading tasks for the current user, separated by disease
        # and role (resident vs faculty) and arbitration tasks
        from sqlalchemy.orm import selectinload
        
        # Get pagination parameters for dual grading tasks - independent pagination for each type and disease
        resident_page = request.args.get('resident_p', default=1, type=int) or 1
        resident_page = max(1, resident_page)
        faculty_page = request.args.get('faculty_p', default=1, type=int) or 1
        faculty_page = max(1, faculty_page)
        arbitration_page = request.args.get('arbitration_p', default=1, type=int) or 1
        arbitration_page = max(1, arbitration_page)
        dual_per_page = 3  # Changed to 3 items per page
        
        # Get user role to determine which tasks to show
        is_admin = current_user.has_role('admin')
        is_resident = current_user.has_role('optometrist')
        is_faculty = current_user.has_role('ophthalmologist')
        
        # Initialize task dictionaries and counts
        resident_tasks = {}
        faculty_tasks = {}
        arbitration_tasks = {}
        resident_totals = {}
        faculty_totals = {}
        arbitration_totals = {}
        resident_total_pages = {}
        faculty_total_pages = {}
        arbitration_total_pages = {}
        
        # Fetch tasks based on user role with pagination per disease
        if is_admin or is_resident:
            # Get user's lab unit IDs within the session context
            user_lab_unit_ids = []
            if hasattr(current_user, 'id'):
                # Load user with lab_units relationship within the current session
                user_with_lab_units = db.query(User).options(selectinload(User.lab_units)).filter(User.id == current_user.id).first()
                if user_with_lab_units and user_with_lab_units.lab_units:
                    user_lab_unit_ids = [lu.id for lu in user_with_lab_units.lab_units]
            
            # Get all diseases to ensure we have entries for all diseases
            all_diseases = db.query(Disease).all()
            
            # Get pending tasks for residents, grouped by disease
            for disease in all_diseases:
                # Create disease-specific page parameter
                disease_resident_page = request.args.get(f'resident_{disease.name.replace(" ", "_")}_p', default=1, type=int) or 1
                disease_resident_page = max(1, disease_resident_page)
                
                resident_query = db.query(GradingTask).options(
                    selectinload(GradingTask.disease),
                    selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter),
                    selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.lab_unit),
                    selectinload(GradingTask.lab_unit)  # Include lab_unit information
                ).filter(
                    GradingTask.state == 'pending',
                    GradingTask.disease_id == disease.id
                )
                
                # Filter by user's lab units if available
                if user_lab_unit_ids:
                    resident_query = resident_query.filter(GradingTask.lab_unit_id.in_(user_lab_unit_ids))
                
                resident_totals[disease.name] = resident_query.count()
                resident_total_pages[disease.name] = max(1, (resident_totals[disease.name] + dual_per_page - 1) // dual_per_page) if resident_totals[disease.name] else 1
                
                resident_task_list = (
                    resident_query
                    .offset((disease_resident_page - 1) * dual_per_page)
                    .limit(dual_per_page)
                    .all()
                )
                
                resident_tasks[disease.name] = resident_task_list
        
        if is_admin or is_faculty:
            # Get user's lab unit IDs within the session context
            user_lab_unit_ids = []
            if hasattr(current_user, 'id'):
                # Load user with lab_units relationship within the current session
                user_with_lab_units = db.query(User).options(selectinload(User.lab_units)).filter(User.id == current_user.id).first()
                if user_with_lab_units and user_with_lab_units.lab_units:
                    user_lab_unit_ids = [lu.id for lu in user_with_lab_units.lab_units]
            
            # Get all diseases to ensure we have entries for all diseases
            all_diseases = db.query(Disease).all()
            
            # Get tasks where resident has completed grading (ready for faculty review), grouped by disease
            for disease in all_diseases:
                # Create disease-specific page parameter
                disease_faculty_page = request.args.get(f'faculty_{disease.name.replace(" ", "_")}_p', default=1, type=int) or 1
                disease_faculty_page = max(1, disease_faculty_page)
                
                faculty_query = db.query(GradingTask).options(
                    selectinload(GradingTask.disease),
                    selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter),
                    selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.lab_unit),
                    selectinload(GradingTask.lab_unit)  # Include lab_unit information
                ).filter(
                    GradingTask.state == 'resident_done',
                    GradingTask.disease_id == disease.id
                )
                
                # Filter by user's lab units if available
                if user_lab_unit_ids:
                    faculty_query = faculty_query.filter(GradingTask.lab_unit_id.in_(user_lab_unit_ids))
                
                faculty_totals[disease.name] = faculty_query.count()
                faculty_total_pages[disease.name] = max(1, (faculty_totals[disease.name] + dual_per_page - 1) // dual_per_page) if faculty_totals[disease.name] else 1
                
                faculty_task_list = (
                    faculty_query
                    .offset((disease_faculty_page - 1) * dual_per_page)
                    .limit(dual_per_page)
                    .all()
                )
                
                faculty_tasks[disease.name] = faculty_task_list
        
        if is_admin:
            # Get user's lab unit IDs within the session context
            user_lab_unit_ids = []
            if hasattr(current_user, 'id'):
                # Load user with lab_units relationship within the current session
                user_with_lab_units = db.query(User).options(selectinload(User.lab_units)).filter(User.id == current_user.id).first()
                if user_with_lab_units and user_with_lab_units.lab_units:
                    user_lab_unit_ids = [lu.id for lu in user_with_lab_units.lab_units]
            
            # Get tasks that need arbitration
            arbitration_query = db.query(GradingTask).options(
                selectinload(GradingTask.disease),
                selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter),
                selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.lab_unit),
                selectinload(GradingTask.lab_unit)  # Include lab_unit information
            ).filter(GradingTask.state == 'arbitration')
            
            # Filter by user's lab units if available
            if user_lab_unit_ids:
                arbitration_query = arbitration_query.filter(GradingTask.lab_unit_id.in_(user_lab_unit_ids))
            
            # Filter by user's lab units if available
            if user_lab_unit_ids:
                arbitration_query = arbitration_query.filter(GradingTask.lab_unit_id.in_(user_lab_unit_ids))
            
            arbitration_total = arbitration_query.count()
            arbitration_total_pages_global = max(1, (arbitration_total + dual_per_page - 1) // dual_per_page) if arbitration_total else 1
            
            arbitration_task_list = (
                arbitration_query
                .offset((arbitration_page - 1) * dual_per_page)
                .limit(dual_per_page)
                .all()
            )
            
            arbitration_tasks['all'] = arbitration_task_list
            arbitration_totals['all'] = arbitration_total
            arbitration_total_pages['all'] = arbitration_total_pages_global
                
        # Calculate pagination URLs for each disease and task type
        def build_pagination_urls(base_url, page, total_pages, page_param):
            prev_url = url_for(base_url, **{page_param: page-1}) if page > 1 else None
            next_url = url_for(base_url, **{page_param: page+1}) if page < total_pages else None
            return prev_url, next_url
        
        # For resident tasks
        resident_prev_urls = {}
        resident_next_urls = {}
        for disease_name in resident_tasks.keys():
            # Create disease-specific page parameter
            page_param = f'resident_{disease_name.replace(" ", "_")}_p'
            disease_resident_page = request.args.get(page_param, default=1, type=int) or 1
            disease_resident_page = max(1, disease_resident_page)
            
            resident_prev_urls[disease_name], resident_next_urls[disease_name] = build_pagination_urls(
                'grading.index', disease_resident_page, resident_total_pages.get(disease_name, 1), page_param
            )
        
        # For faculty tasks
        faculty_prev_urls = {}
        faculty_next_urls = {}
        for disease_name in faculty_tasks.keys():
            # Create disease-specific page parameter
            page_param = f'faculty_{disease_name.replace(" ", "_")}_p'
            disease_faculty_page = request.args.get(page_param, default=1, type=int) or 1
            disease_faculty_page = max(1, disease_faculty_page)
            
            faculty_prev_urls[disease_name], faculty_next_urls[disease_name] = build_pagination_urls(
                'grading.index', disease_faculty_page, faculty_total_pages.get(disease_name, 1), page_param
            )
        
        # For arbitration tasks
        arbitration_prev_url, arbitration_next_url = build_pagination_urls(
            'grading.index', arbitration_page, arbitration_total_pages.get('all', 1), 'arbitration_p'
        )
    finally:
        db.close()

    return render_template(
        "grading/index.html",
        type_counts=type_counts,
        my_items=items_mine,
        my_total=total_mine,
        my_page=page,
        my_total_pages=total_pages_mine,
        my_prev_url=mine_prev_url,
        my_next_url=mine_next_url,
        gfor=gfor,
        task_type=task_type,
        resident_tasks=resident_tasks,
        faculty_tasks=faculty_tasks,
        arbitration_tasks=arbitration_tasks,
        resident_totals=resident_totals,
        faculty_totals=faculty_totals,
        arbitration_totals=arbitration_totals,
        resident_total_pages=resident_total_pages,
        faculty_total_pages=faculty_total_pages,
        arbitration_total_pages=arbitration_total_pages,
        resident_prev_urls=resident_prev_urls,
        resident_next_urls=resident_next_urls,
        faculty_prev_urls=faculty_prev_urls,
        faculty_next_urls=faculty_next_urls,
        arbitration_prev_url=arbitration_prev_url,
        arbitration_next_url=arbitration_next_url,
        resident_page=resident_page,
        faculty_page=faculty_page,
        arbitration_page=arbitration_page,
        is_admin=is_admin,
        is_resident=is_resident,
        is_faculty=is_faculty
    )