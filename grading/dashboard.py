from collections.abc import Mapping

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, desc, distinct, func


from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.dashboard_service import grader_eligibility_dto, grading_history_page
from grading_allocation.dashboard import list_project_encounter_set_queues
from models import PatientEncounters, EncounterFile, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User, Grade
from utils.dualGradingKPIs import get_user_kpi_pending_task_count_data
from utils.dualGradingKPIs import get_user_kpi_completed_task_count_data
from utils.dualGradingKPIs import get_user_kpi_linked_followup_counts
from utils.dualGradingKPIs import get_user_task_tracker_kpi_data
from utils.dualGradingEligibility import get_user_grading_eligibility_details

 
def _build_history_panel_context(
    db,
    *,
    user_id: int | None,
    page: int,
    per_page: int,
    filter_date: str | None,
    history_type: str,
    disease_id: int | None,
):
    history = grading_history_page(
        db,
        user_id=user_id,
        requested_date=filter_date,
        history_type=history_type,
        disease_id=disease_id,
        page=page,
        per_page=per_page,
    )
    def history_url(*, selected_date=None, selected_page=1):
        params = {
            "date": selected_date or history.selected_date,
            "history_type": history.history_type,
        }
        if history.disease_id:
            params["disease_id"] = history.disease_id
        if selected_page > 1:
            params["p"] = selected_page
        return url_for("grading.index", **params)

    return {
        "history": history.to_dict(),
        "my_prev_url": (
            history_url(selected_date=history.previous_date)
            if history.previous_date else None
        ),
        "my_next_url": (
            history_url(selected_date=history.next_date)
            if history.next_date else None
        ),
        "page_prev_url": (
            history_url(selected_page=history.page - 1)
            if history.page > 1 else None
        ),
        "page_next_url": (
            history_url(selected_page=history.page + 1)
            if history.page < history.total_pages else None
        ),
    }


@roles_required("resident", "ophthalmologist")
def index():
    # Stats + most recent encounter with an ungraded glaucoma image
    with transaction_scope() as db:
        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 12
        filter_date = request.args.get('date', default=None, type=str)
        history_type = request.args.get("history_type", default="all", type=str)
        disease_id = request.args.get("disease_id", default=None, type=int)
        try:
            history_panel_context = _build_history_panel_context(
                db,
                user_id=getattr(current_user, 'id', None),
                page=page,
                per_page=per_page,
                filter_date=filter_date,
                history_type=history_type,
                disease_id=disease_id,
            )
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("grading.index"))

        if request.headers.get("HX-Request") == "true":
            return render_template("grading/_history_panel.html", **history_panel_context)

        # Get dual grading tasks for the current user, separated by disease
        # and role (resident vs resident2) and arbitration tasks
        
        # Get user role to determine which tasks to show
        # For dual grading, determine eligibility based on user's eligibility matrix rather than specific 'resident' role
        # Any user with role that allows them to grade (resident, ophthalmologist) can do resident grading
        raw_user_eligibility = get_user_grading_eligibility_details(db, current_user.id)
        eligibility = grader_eligibility_dto(db, user_id=current_user.id)
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
        project_encounter_set_queues = list_project_encounter_set_queues(
            db,
            user_id=current_user.id,
        )
        kpi_pending_data = get_user_kpi_pending_task_count_data(
            db,
            current_user.id,
            exclude_enforced_project_encounter_sets=True,
        )
        
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
        task_tracker_kpi = get_user_task_tracker_kpi_data(db, current_user.id)

        linked_followup_counts_by_disease = get_user_kpi_linked_followup_counts(
            db,
            current_user.id,
            exclude_enforced_project_encounter_sets=True,
        )
        
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
    return render_template(
        "grading/index.html",
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
        task_tracker_kpi=task_tracker_kpi,
        user_eligibility=user_eligibility,
        grading_eligibility=eligibility,
        diseases=diseases_data,
        linked_followup_counts_by_disease=linked_followup_counts_by_disease,
        project_encounter_set_queues=[
            queue.to_dict() for queue in project_encounter_set_queues
        ],
        **history_panel_context,
    )
