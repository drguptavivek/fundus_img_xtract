from collections.abc import Mapping

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, desc, distinct, func


from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User, Grade
from utils.dualGradingKPIs import get_user_kpi_pending_task_count_data
from utils.dualGradingKPIs import get_user_kpi_completed_task_count_data
from utils.dualGradingKPIs import get_user_kpi_linked_followup_counts
from utils.dualGradingFetchDetailUtils import get_user_gradings_with_details
from utils.dualGradingEligibility import get_user_grading_eligibility_details

 

@roles_required("resident", "ophthalmologist")
def index():
    # Stats + most recent encounter with an ungraded glaucoma image
    db = Session()
    try:
        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 50
        filter_date = request.args.get('date', default=None, type=str)
        
        # Get user's gradings with details using pagination
        my_items, total_mine = get_user_gradings_with_details(
            db,
            user_id=getattr(current_user, 'id', None),
            page=page,
            per_page=per_page,
            filter_date=filter_date,
            exclude_role_slots={'review'}
        )
        
        # Get all available grading dates for this user
        available_dates = db.query(
            func.date(Grade.created_at).label('grading_date')
        ).filter(
            Grade.grader_user_id == getattr(current_user, 'id', None)
        ).group_by(
            func.date(Grade.created_at)
        ).order_by(
            desc(func.date(Grade.created_at))
        ).all()
        
        # Convert to list of date strings
        date_list = [date[0] for date in available_dates]
        
        # Find previous and next dates
        prev_date = None
        next_date = None
        
        if filter_date and filter_date in date_list:
            current_index = date_list.index(filter_date)
            if current_index < len(date_list) - 1:
                prev_date = date_list[current_index + 1]
            if current_index > 0:
                next_date = date_list[current_index - 1]
        # Build navigation URLs
        mine_prev_url = url_for('grading.index', date=prev_date) if prev_date else None
        mine_next_url = url_for('grading.index', date=next_date) if next_date else None
        
        # Calculate total pages for pagination within the selected date
        total_pages_mine = max(1, (total_mine + per_page - 1) // per_page) if total_mine else 1
        
        # Build page navigation URLs that preserve the date filter
        page_prev_url = None
        page_next_url = None
        
        if total_pages_mine > 1:
            if page > 1:
                page_params = {'p': page - 1}
                if filter_date:
                    page_params['date'] = filter_date
                page_prev_url = url_for('grading.index', **page_params)
            
            if page < total_pages_mine:
                page_params = {'p': page + 1}
                if filter_date:
                    page_params['date'] = filter_date
                page_next_url = url_for('grading.index', **page_params)
        
        # Get impression counts for display from the gradings data
        type_counts = {}
        for item in my_items:
            grade_for = item.get('disease_name', 'Unknown')
            type_counts[grade_for] = type_counts.get(grade_for, 0) + 1

        # Get dual grading tasks for the current user, separated by disease
        # and role (resident vs resident2) and arbitration tasks
        
        # Get user role to determine which tasks to show
        # For dual grading, determine eligibility based on user's eligibility matrix rather than specific 'resident' role
        # Any user with role that allows them to grade (resident, ophthalmologist) can do resident grading
        raw_user_eligibility = get_user_grading_eligibility_details(db, current_user.id)
        user_eligibility: dict[str, dict[str, dict[str, list[str]]]] = {}
        if isinstance(raw_user_eligibility, Mapping):
            for hospital_name, lab_units in raw_user_eligibility.items():
                normalized_lab_units: dict[str, dict[str, list[str]]] = {}
                if not isinstance(lab_units, Mapping):
                    continue
                for lab_unit_name, diseases in lab_units.items():
                    normalized_diseases: dict[str, list[str]] = {}
                    if not isinstance(diseases, Mapping):
                        continue
                    for disease_name, roles in diseases.items():
                        seen_roles: set[str] = set()
                        display_roles: list[str] = []
                        if isinstance(roles, (list, tuple, set)):
                            iterable_roles = roles
                        else:
                            iterable_roles = [roles]
                        for role in iterable_roles:
                            if not isinstance(role, str):
                                continue
                            role_lower = role.lower()
                            if role_lower in {"resident", "resident2"}:
                                display_role = "Resident"
                            else:
                                display_role = role.capitalize() if role.islower() else role
                            key = display_role.lower()
                            if key not in seen_roles:
                                seen_roles.add(key)
                                display_roles.append(display_role)
                        normalized_diseases[disease_name] = display_roles
                    normalized_lab_units[lab_unit_name] = normalized_diseases
                user_eligibility[hospital_name] = normalized_lab_units
        else:
            user_eligibility = {}

        # Check if user has any resident eligibility
        has_resident_eligibility = False
        for hospital_data in user_eligibility.values():
            for lab_unit_data in hospital_data.values():
                for diseases_roles in lab_unit_data.values():
                    if 'Resident' in diseases_roles:
                        has_resident_eligibility = True
                        break
                if has_resident_eligibility:
                    break
            if has_resident_eligibility:
                break
        
        # is_resident means user has permission to do resident-level grading
        is_resident = has_resident_eligibility and (current_user.has_role('resident') or current_user.has_role('ophthalmologist'))
        is_resident2 = current_user.has_role('ophthalmologist')
        
        # Initialize KPIs
        kpi_resident_pending = 0
        kpi_resident2_pending = 0
        kpi_arbitration_pending = 0
        
        # Initialize disease-specific KPIs
        kpi_resident_by_disease = {}
        kpi_resident2_by_disease = {}
        kpi_arbitration_by_disease = {}
        
        # Initialize completed KPIs
        kpi_resident_completed = 0
        kpi_resident2_completed = 0
        kpi_arbitration_completed = 0
        
        # Initialize disease-specific completed KPIs
        kpi_resident_completed_by_disease = {}
        kpi_resident2_completed_by_disease = {}
        kpi_arbitration_completed_by_disease = {}
        
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
        
        kpi_arbitration_breakdown_by_disease = {}

        # Process pending KPI data from the utility function
        for disease in all_diseases:
            disease_name = disease.name
            
            # Initialize disease-specific KPIs
            kpi_resident_by_disease[disease_name] = 0
            kpi_resident2_by_disease[disease_name] = 0
            kpi_arbitration_by_disease[disease_name] = 0
            kpi_arbitration_breakdown_by_disease[disease_name] = {}
            
            # Get data for this disease if available
            if disease_name in kpi_pending_data:
                disease_kpi = kpi_pending_data[disease_name]
                kpi_resident_by_disease[disease_name] = disease_kpi.get('resident_pending', 0)
                kpi_resident2_by_disease[disease_name] = disease_kpi.get('resident2_pending', 0)
                kpi_arbitration_by_disease[disease_name] = disease_kpi.get('arbitration_pending', 0)
                kpi_arbitration_breakdown_by_disease[disease_name] = disease_kpi.get('arbitration_breakdown', {})
                
                # Add to totals
                kpi_resident_pending += disease_kpi.get('resident_pending', 0)
                kpi_resident2_pending += disease_kpi.get('resident2_pending', 0)
                kpi_arbitration_pending += disease_kpi.get('arbitration_pending', 0)
        
        # Calculate completed KPIs using the utility function
        kpi_completed_data = get_user_kpi_completed_task_count_data(db, current_user.id)

        linked_followup_counts_by_disease = get_user_kpi_linked_followup_counts(db, current_user.id)
        
        # Process completed KPI data from the utility function
        for disease in all_diseases:
            disease_name = disease.name
            
            # Initialize disease-specific completed KPIs
            kpi_resident_completed_by_disease[disease_name] = 0
            kpi_resident2_completed_by_disease[disease_name] = 0
            kpi_arbitration_completed_by_disease[disease_name] = 0
            
            # Get data for this disease if available
            if disease_name in kpi_completed_data:
                disease_kpi = kpi_completed_data[disease_name]
                kpi_resident_completed_by_disease[disease_name] = disease_kpi.get('resident_completed', 0)
                kpi_resident2_completed_by_disease[disease_name] = disease_kpi.get('resident2_completed', 0)
                kpi_arbitration_completed_by_disease[disease_name] = disease_kpi.get('arbitration_completed', 0)
                
                # Add to totals
                kpi_resident_completed += disease_kpi.get('resident_completed', 0)
                kpi_resident2_completed += disease_kpi.get('resident2_completed', 0)
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
        page_prev_url=page_prev_url,
        page_next_url=page_next_url,
        filter_date=filter_date,
        is_resident=is_resident,
        is_resident2=is_resident2,
        kpi_resident_pending=kpi_resident_pending,
        kpi_resident2_pending=kpi_resident2_pending,
        kpi_arbitration_pending=kpi_arbitration_pending,
        kpi_resident_by_disease=kpi_resident_by_disease,
        kpi_resident2_by_disease=kpi_resident2_by_disease,
        kpi_arbitration_by_disease=kpi_arbitration_by_disease,
        kpi_arbitration_breakdown_by_disease=kpi_arbitration_breakdown_by_disease,
        kpi_resident_completed=kpi_resident_completed,
        kpi_resident2_completed=kpi_resident2_completed,
        kpi_arbitration_completed=kpi_arbitration_completed,
        kpi_resident_completed_by_disease=kpi_resident_completed_by_disease,
        kpi_resident2_completed_by_disease=kpi_resident2_completed_by_disease,
        kpi_arbitration_completed_by_disease=kpi_arbitration_completed_by_disease,
        user_eligibility=user_eligibility,
        diseases=diseases_data,
        linked_followup_counts_by_disease=linked_followup_counts_by_disease,
    )
