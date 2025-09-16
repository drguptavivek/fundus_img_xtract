from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func
import random
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User
from utils.dualGradingUtils import get_all_pending_resident_for_labUnit_disease, get_all_pending_faculty_for_labUnit_disease, get_all_pending_arbitration_for_labUnit_disease, get_all_pending_resident_for_disease, get_all_pending_faculty_for_disease, get_all_pending_arbitration_for_disease
from utils.userGradingsDone import get_user_gradings_with_details
from utils.masterUtils import get_all_diseases


@roles_required("admin", "resident", "ophthalmologist")
def index():
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
        
        # Initialize KPIs
        kpi_resident_pending = 0
        kpi_faculty_pending = 0
        kpi_arbitration_pending = 0
        
        # Initialize disease-specific KPIs
        kpi_resident_by_disease = {}
        kpi_faculty_by_disease = {}
        kpi_arbitration_by_disease = {}
        
        # Get user's lab unit IDs
        user_lab_unit_ids = []
        if hasattr(current_user, 'id'):
            # Load user with lab_units relationship within the current session
            user_with_lab_units = db.query(User).options(joinedload(User.lab_units)).filter(User.id == current_user.id).first()
            if user_with_lab_units and user_with_lab_units.lab_units:
                user_lab_unit_ids = [lu.id for lu in user_with_lab_units.lab_units]
        
        # Get all diseases to ensure we have entries for all diseases
        all_diseases = db.query(Disease).all()
        
        # Calculate KPIs - total pending tasks across all diseases and lab units
        for disease in all_diseases:
            disease_name = disease.name
            
            # Initialize disease-specific KPIs
            kpi_resident_by_disease[disease_name] = 0
            kpi_faculty_by_disease[disease_name] = 0
            kpi_arbitration_by_disease[disease_name] = 0
            
            # Calculate disease-specific KPIs
            if is_admin or is_resident:
                resident_stats = get_all_pending_resident_for_disease(current_user.id, disease.id)
                kpi_resident_pending += resident_stats['total']
                kpi_resident_by_disease[disease_name] = resident_stats['total']
                
            if is_admin or is_faculty:
                faculty_stats = get_all_pending_faculty_for_disease(current_user.id, disease.id)
                kpi_faculty_pending += faculty_stats['total']
                kpi_faculty_by_disease[disease_name] = faculty_stats['total']
                
            if is_admin:
                arbitration_stats = get_all_pending_arbitration_for_disease(current_user.id, disease.id)
                kpi_arbitration_pending += arbitration_stats['total']
                kpi_arbitration_by_disease[disease_name] = arbitration_stats['total']
        
        # Get pending tasks for residents, grouped by disease using utility functions
        if is_admin or is_resident:
            for disease in all_diseases:
                # For each lab unit the user belongs to, get pending resident tasks
                for lab_unit_id in user_lab_unit_ids:
                    # Use utility function to get pending resident tasks
                    resident_stats = get_all_pending_resident_for_labUnit_disease(current_user.id, lab_unit_id, disease.id)
                    
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
                    faculty_stats = get_all_pending_faculty_for_labUnit_disease(current_user.id, lab_unit_id, disease.id)
                    
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
                    arbitration_stats = get_all_pending_arbitration_for_labUnit_disease(current_user.id, lab_unit_id, disease.id)
                    
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
        is_faculty=is_faculty,
        kpi_resident_pending=kpi_resident_pending,
        kpi_faculty_pending=kpi_faculty_pending,
        kpi_arbitration_pending=kpi_arbitration_pending,
        kpi_resident_by_disease=kpi_resident_by_disease,
        kpi_faculty_by_disease=kpi_faculty_by_disease,
        kpi_arbitration_by_disease=kpi_arbitration_by_disease
    )