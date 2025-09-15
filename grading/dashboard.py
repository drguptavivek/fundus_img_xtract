from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func
import random
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User
from utils.dualGradingUtils import get_all_pending_resident, get_all_pending_faculty, get_all_pending_arbitration
from utils.userGradingsDone import get_user_gradings_with_details


@roles_required("admin", "resident", "ophthalmologist")
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
        # Filter my gradings by grading type only (task type filter removed as only dual grading tasks are created)
        gfor = (request.args.get('gfor') or 'all').strip().lower()
        my_q = (
            db.query(ImageGrading)
              .options(
                  joinedload(ImageGrading.image),
                  joinedload(ImageGrading.direct_image)
              )
              .filter(ImageGrading.grader_user_id == getattr(current_user, 'id', None))
              .filter(ImageGrading.task_id.isnot(None))  # Only show dual grading tasks
              .order_by(ImageGrading.updated_at.desc())
        )
        if gfor and gfor != 'all':
            my_q = my_q.filter(ImageGrading.graded_for == gfor)
        total_mine = my_q.count()
        items_mine = (
            my_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        total_pages_mine = max(1, (total_mine + per_page - 1) // per_page) if total_mine else 1
        mine_prev_url = url_for('grading.index', p=page-1, gfor=gfor) if page > 1 else None
        mine_next_url = url_for('grading.index', p=page+1, gfor=gfor) if page < total_pages_mine else None
        
        # Get dual grading tasks for the current user, separated by disease
        # and role (resident vs faculty) and arbitration tasks
        
        # Get user role to determine which tasks to show
        is_admin = current_user.has_role('admin')
        is_resident = current_user.has_role('resident')
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
        
        # Get user's lab unit IDs
        user_lab_unit_ids = []
        if hasattr(current_user, 'id'):
            # Load user with lab_units relationship within the current session
            user_with_lab_units = db.query(User).options(joinedload(User.lab_units)).filter(User.id == current_user.id).first()
            if user_with_lab_units and user_with_lab_units.lab_units:
                user_lab_unit_ids = [lu.id for lu in user_with_lab_units.lab_units]
        
        # Get all diseases to ensure we have entries for all diseases
        all_diseases = db.query(Disease).all()
        
        # Get pending tasks for residents, grouped by disease using utility functions
        if is_admin or is_resident:
            for disease in all_diseases:
                # For each lab unit the user belongs to, get pending resident tasks
                for lab_unit_id in user_lab_unit_ids:
                    # Use utility function to get pending resident tasks
                    resident_stats = get_all_pending_resident(current_user.id, lab_unit_id, disease.id)
                    
                    # Store the results
                    key = f"{disease.name} - {lab_unit_id}"
                    resident_totals[key] = resident_stats['total']
                    # For pagination, we'll use a simple approach (1 page for now)
                    resident_total_pages[key] = 1
                    
                    # Store first task info if available
                    if resident_stats['first_task_id']:
                        # Create a simple task object for display
                        task_info = {
                            'id': resident_stats['first_task_id'],
                            'lab_unit_id': resident_stats['first_task_lab_unit_id'],
                            'image_uuid': resident_stats['first_task_img_uuid']
                        }
                        resident_tasks[key] = [task_info]  # Store as list for consistency
        
        # Get tasks where resident has completed grading (ready for faculty review), grouped by disease
        if is_admin or is_faculty:
            for disease in all_diseases:
                # For each lab unit the user belongs to, get pending faculty tasks
                for lab_unit_id in user_lab_unit_ids:
                    # Use utility function to get pending faculty tasks
                    faculty_stats = get_all_pending_faculty(current_user.id, lab_unit_id, disease.id)
                    
                    # Store the results
                    key = f"{disease.name} - {lab_unit_id}"
                    faculty_totals[key] = faculty_stats['total']
                    # For pagination, we'll use a simple approach (1 page for now)
                    faculty_total_pages[key] = 1
                    
                    # Store first task info if available
                    if faculty_stats['first_task_id']:
                        # Create a simple task object for display
                        task_info = {
                            'id': faculty_stats['first_task_id'],
                            'lab_unit_id': faculty_stats['first_task_lab_unit_id'],
                            'image_uuid': faculty_stats['first_task_img_uuid']
                        }
                        faculty_tasks[key] = [task_info]  # Store as list for consistency
        
        # Get tasks that need arbitration
        if is_admin:
            for disease in all_diseases:
                # For each lab unit the user belongs to, get pending arbitration tasks
                for lab_unit_id in user_lab_unit_ids:
                    # Use utility function to get pending arbitration tasks
                    arbitration_stats = get_all_pending_arbitration(current_user.id, lab_unit_id, disease.id)
                    
                    # Store the results
                    key = f"{disease.name} - {lab_unit_id}"
                    arbitration_totals[key] = arbitration_stats['total']
                    # For pagination, we'll use a simple approach (1 page for now)
                    arbitration_total_pages[key] = 1
                    
                    # Store first task info if available
                    if arbitration_stats['first_task_id']:
                        # Create a simple task object for display
                        task_info = {
                            'id': arbitration_stats['first_task_id'],
                            'lab_unit_id': arbitration_stats['first_task_lab_unit_id'],
                            'image_uuid': arbitration_stats['first_task_img_uuid']
                        }
                        arbitration_tasks[key] = [task_info]  # Store as list for consistency
                        
        # Calculate pagination URLs for each disease and task type
        def build_pagination_urls(base_url, page, total_pages, page_param):
            prev_url = url_for(base_url, **{page_param: page-1}) if page > 1 else None
            next_url = url_for(base_url, **{page_param: page+1}) if page < total_pages else None
            return prev_url, next_url
        
        # For resident tasks
        resident_prev_urls = {}
        resident_next_urls = {}
        for key in resident_tasks.keys():
            # Create key-specific page parameter
            page_param = f'resident_{key.replace(" ", "_").replace("-", "_")}_p'
            page = request.args.get(page_param, default=1, type=int) or 1
            page = max(1, page)
            
            resident_prev_urls[key], resident_next_urls[key] = build_pagination_urls(
                'grading.index', page, resident_total_pages.get(key, 1), page_param
            )
        
        # For faculty tasks
        faculty_prev_urls = {}
        faculty_next_urls = {}
        for key in faculty_tasks.keys():
            # Create key-specific page parameter
            page_param = f'faculty_{key.replace(" ", "_").replace("-", "_")}_p'
            page = request.args.get(page_param, default=1, type=int) or 1
            page = max(1, page)
            
            faculty_prev_urls[key], faculty_next_urls[key] = build_pagination_urls(
                'grading.index', page, faculty_total_pages.get(key, 1), page_param
            )
        
        # For arbitration tasks
        arbitration_prev_urls = {}
        arbitration_next_urls = {}
        for key in arbitration_tasks.keys():
            # Create key-specific page parameter
            page_param = f'arbitration_{key.replace(" ", "_").replace("-", "_")}_p'
            page = request.args.get(page_param, default=1, type=int) or 1
            page = max(1, page)
            
            arbitration_prev_urls[key], arbitration_next_urls[key] = build_pagination_urls(
                'grading.index', page, arbitration_total_pages.get(key, 1), page_param
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
        arbitration_prev_urls=arbitration_prev_urls,
        arbitration_next_urls=arbitration_next_urls,
        is_admin=is_admin,
        is_resident=is_resident,
        is_faculty=is_faculty
    )