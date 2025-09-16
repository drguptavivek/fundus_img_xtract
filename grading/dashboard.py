from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func
import random
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User
from utils.dualGradingUtils import get_user_kpi_pending_task_count_data
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
        
        # Initialize KPIs
        kpi_resident_pending = 0
        kpi_faculty_pending = 0
        kpi_arbitration_pending = 0
        
        # Initialize disease-specific KPIs
        kpi_resident_by_disease = {}
        kpi_faculty_by_disease = {}
        kpi_arbitration_by_disease = {}
        
        # Get all diseases to ensure we have entries for all diseases
        all_diseases = db.query(Disease).all()
        
        # Calculate KPIs using the utility function
        kpi_data = get_user_kpi_pending_task_count_data(current_user.id)
        
        # Process KPI data from the utility function
        for disease in all_diseases:
            disease_name = disease.name
            
            # Initialize disease-specific KPIs
            kpi_resident_by_disease[disease_name] = 0
            kpi_faculty_by_disease[disease_name] = 0
            kpi_arbitration_by_disease[disease_name] = 0
            
            # Get data for this disease if available
            if disease_name in kpi_data:
                disease_kpi = kpi_data[disease_name]
                kpi_resident_by_disease[disease_name] = disease_kpi.get('resident_pending', 0)
                kpi_faculty_by_disease[disease_name] = disease_kpi.get('faculty_pending', 0)
                kpi_arbitration_by_disease[disease_name] = disease_kpi.get('arbitration_pending', 0)
                
                # Add to totals
                kpi_resident_pending += disease_kpi.get('resident_pending', 0)
                kpi_faculty_pending += disease_kpi.get('faculty_pending', 0)
                kpi_arbitration_pending += disease_kpi.get('arbitration_pending', 0)
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