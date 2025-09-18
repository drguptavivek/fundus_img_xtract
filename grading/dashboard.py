from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func
import random
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User
from utils.dualGradingKPIs import get_user_kpi_pending_task_count_data
from utils.dualGradingKPIs import get_user_kpi_completed_task_count_data
from utils.gradeUtils import get_user_gradings_with_details
from utils.dualGradingEligibility import get_user_grading_eligibility_details
from utils.masterUtils import get_all_diseases


@roles_required("resident", "ophthalmologist")
def index():
    # Stats + most recent encounter with an ungraded glaucoma image
    db = Session()
    try:
        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 20
        
        # Get user's gradings with details using pagination
        my_items, total_mine = get_user_gradings_with_details(
            db,
            user_id=getattr(current_user, 'id', None),
            page=page,
            per_page=per_page
        )
        
        total_pages_mine = max(1, (total_mine + per_page - 1) // per_page) if total_mine else 1
        mine_prev_url = url_for('grading.index', p=page-1) if page > 1 else None
        mine_next_url = url_for('grading.index', p=page+1) if page < total_pages_mine else None
        
        # Get impression counts for display from the gradings data
        type_counts = {}
        for item in my_items:
            grade_for = item.get('disease_name', 'Unknown')
            type_counts[grade_for] = type_counts.get(grade_for, 0) + 1

        # Get dual grading tasks for the current user, separated by disease
        # and role (resident vs faculty) and arbitration tasks
        
        # Get user role to determine which tasks to show
        is_resident = current_user.has_role('resident')
        is_faculty = current_user.has_role('ophthalmologist')
        
        # Initialize KPIs
        kpi_resident_pending = 0
        kpi_faculty_pending = 0
        kpi_arbitration_pending = 0
        
        # Initialize disease-specific KPIs
        kpi_resident_by_disease = {}
        kpi_faculty_by_disease = {}
        kpi_arbitration_by_disease = {}
        
        # Initialize completed KPIs
        kpi_resident_completed = 0
        kpi_faculty_completed = 0
        kpi_arbitration_completed = 0
        
        # Initialize disease-specific completed KPIs
        kpi_resident_completed_by_disease = {}
        kpi_faculty_completed_by_disease = {}
        kpi_arbitration_completed_by_disease = {}
        
        # Get user's grading eligibility details
        user_eligibility = get_user_grading_eligibility_details(db, current_user.id)
        
        # Get all diseases to ensure we have entries for all diseases
        all_diseases = db.query(Disease).all()
        diseases_data = [
            {
                'id': disease.id,
                'name': disease.name
            }
            for disease in all_diseases
        ]
        
        # Calculate pending KPIs using the utility function
        kpi_pending_data = get_user_kpi_pending_task_count_data(db, current_user.id)
        
        # Process pending KPI data from the utility function
        for disease in all_diseases:
            disease_name = disease.name
            
            # Initialize disease-specific KPIs
            kpi_resident_by_disease[disease_name] = 0
            kpi_faculty_by_disease[disease_name] = 0
            kpi_arbitration_by_disease[disease_name] = 0
            
            # Get data for this disease if available
            if disease_name in kpi_pending_data:
                disease_kpi = kpi_pending_data[disease_name]
                kpi_resident_by_disease[disease_name] = disease_kpi.get('resident_pending', 0)
                kpi_faculty_by_disease[disease_name] = disease_kpi.get('faculty_pending', 0)
                kpi_arbitration_by_disease[disease_name] = disease_kpi.get('arbitration_pending', 0)
                
                # Add to totals
                kpi_resident_pending += disease_kpi.get('resident_pending', 0)
                kpi_faculty_pending += disease_kpi.get('faculty_pending', 0)
                kpi_arbitration_pending += disease_kpi.get('arbitration_pending', 0)
        
        # Calculate completed KPIs using the utility function
        kpi_completed_data = get_user_kpi_completed_task_count_data(db, current_user.id)
        
        # Process completed KPI data from the utility function
        for disease in all_diseases:
            disease_name = disease.name
            
            # Initialize disease-specific completed KPIs
            kpi_resident_completed_by_disease[disease_name] = 0
            kpi_faculty_completed_by_disease[disease_name] = 0
            kpi_arbitration_completed_by_disease[disease_name] = 0
            
            # Get data for this disease if available
            if disease_name in kpi_completed_data:
                disease_kpi = kpi_completed_data[disease_name]
                kpi_resident_completed_by_disease[disease_name] = disease_kpi.get('resident_completed', 0)
                kpi_faculty_completed_by_disease[disease_name] = disease_kpi.get('faculty_completed', 0)
                kpi_arbitration_completed_by_disease[disease_name] = disease_kpi.get('arbitration_completed', 0)
                
                # Add to totals
                kpi_resident_completed += disease_kpi.get('resident_completed', 0)
                kpi_faculty_completed += disease_kpi.get('faculty_completed', 0)
                kpi_arbitration_completed += disease_kpi.get('arbitration_completed', 0)
    finally:
        db.close()

    return render_template(
        "grading/index.html",
        type_counts=type_counts,
        my_items=my_items,
        my_total=total_mine,
        my_page=page,
        my_total_pages=total_pages_mine,
        my_prev_url=mine_prev_url,
        my_next_url=mine_next_url,
        is_resident=is_resident,
        is_faculty=is_faculty,
        kpi_resident_pending=kpi_resident_pending,
        kpi_faculty_pending=kpi_faculty_pending,
        kpi_arbitration_pending=kpi_arbitration_pending,
        kpi_resident_by_disease=kpi_resident_by_disease,
        kpi_faculty_by_disease=kpi_faculty_by_disease,
        kpi_arbitration_by_disease=kpi_arbitration_by_disease,
        kpi_resident_completed=kpi_resident_completed,
        kpi_faculty_completed=kpi_faculty_completed,
        kpi_arbitration_completed=kpi_arbitration_completed,
        kpi_resident_completed_by_disease=kpi_resident_completed_by_disease,
        kpi_faculty_completed_by_disease=kpi_faculty_completed_by_disease,
        kpi_arbitration_completed_by_disease=kpi_arbitration_completed_by_disease,
        user_eligibility=user_eligibility,
        diseases=diseases_data
    )