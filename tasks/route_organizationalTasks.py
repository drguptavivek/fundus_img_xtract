"""Route for organizational tasks page showing all tasks scoped to user's lab units."""

from __future__ import annotations

from flask import render_template, request
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids
from flask_login import current_user

from db_transaction_manager import get_db_session
from utils.taskUtils import get_task_summary
from utils.masterUtils import get_all_diseases
from models import Hospital, LabUnit
from . import bp


@bp.route("/all-tasks", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def all_tasks() -> str:
    """Page to view all tasks scoped to user's lab units with pagination."""
    # Get pagination parameters from request
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # Limit per_page to reasonable values
    per_page = min(max(per_page, 1), 100)  # Between 1 and 100 items per page
    
    # Get filters from request
    status_filter = request.args.get('status', type=str)
    disease_filter = request.args.get('disease', type=int)
    hospital_filter = request.args.get('hospital', type=int)
    lab_unit_filter = request.args.get('lab_unit', type=int)  # Changed to use lab_unit ID
    search_query = request.args.get('search', type=str)
    
    with get_db_session() as db:
        # Get user's lab unit IDs for scoping
        user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        
        # Get paginated tasks using the utility function
        tasks, total_count = get_task_summary(
            db_session=db,
            page=page,
            per_page=per_page,
            lab_unit_ids=user_lab_unit_ids,
            status_filter=status_filter,
            disease_filter=disease_filter,
            hospital_filter=hospital_filter,
            lab_unit_filter=lab_unit_filter, # Using ID-based filter
            search_query=search_query
        )
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page  # Ceiling division
        
        # Get all diseases for the disease filter dropdown
        diseases = get_all_diseases()
        
        # Get all hospitals and lab units (sorted by ID as requested)
        all_hospitals = db.query(Hospital).order_by(Hospital.id).all()
        all_lab_units = db.query(LabUnit).order_by(LabUnit.id).all()
        
        # Filter hospitals to only include those with lab units the user has access to
        if user_lab_unit_ids:
            # Get lab units that user has access to
            user_lab_units = db.query(LabUnit).filter(LabUnit.id.in_(user_lab_unit_ids)).all()
            # Extract unique hospital IDs from user's lab units
            user_hospital_ids = list(set(lu.hospital_id for lu in user_lab_units if lu.hospital_id))
            # Filter hospitals to only those the user has access to (sorted by ID)
            hospitals = [h for h in all_hospitals if h.id in user_hospital_ids]
            # Filter lab units to only those the user has access to (sorted by ID)
            lab_units = [lu for lu in all_lab_units if lu.id in user_lab_unit_ids]
            
        else:
            # User has no lab unit access, show empty lists
            hospitals = []
            lab_units = []
        
        # Prepare context for template
        context = {
            'tasks': tasks,
            'total_count': total_count,
            'current_page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'status_filter': status_filter,
            'disease_filter': disease_filter,
            'hospital_filter': hospital_filter,
            'lab_unit_filter': lab_unit_filter,
            'search_query': search_query,
            'diseases': diseases,
            'hospitals': hospitals,
            'all_lab_units': lab_units,  # Pass filtered lab units to template
            'user_lab_unit_ids': user_lab_unit_ids
        }
        
        # Render template within the same session to avoid detached instance errors
        return render_template("tasks/all_tasks.html", **context)
