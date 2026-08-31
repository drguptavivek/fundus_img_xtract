"""Route for organizational tasks page showing all tasks scoped to user's lab units."""

from __future__ import annotations

from flask import abort, render_template, request, redirect, url_for, flash
from sqlalchemy import select
from auth.roles import roles_required
from flask_login import current_user

from db_transaction_manager import get_db_session
from utils.taskUtils import get_task_summary
from utils.masterUtils import get_all_diseases
from authz.behaviors import clinical_hospitals, clinical_lab_units
from models import Hospital, LabUnit
from . import bp


def _query_int(name: str, *, default: int | None = None, minimum: int = 1) -> int | None:
    """Parse an optional integer query argument without silently dropping it."""
    if name not in request.args:
        return default
    raw_value = request.args.get(name)
    try:
        value = int(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        abort(400, description=f"Invalid {name} filter")
    if value is None or value < minimum:
        abort(400, description=f"Invalid {name} filter")
    return value


@bp.route("/all-tasks", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "optometrist",
    "project_pi",
    "site_pi",
    "project_admin",
    "collaborator",
)
def all_tasks() -> str:
    """Page to view all tasks scoped to user's lab units with pagination."""
    # Get pagination parameters from request
    page = _query_int("page", default=1)
    per_page = _query_int("per_page", default=50)
    
    # Limit per_page to reasonable values
    per_page = min(max(per_page, 1), 100)  # Between 1 and 100 items per page
    
    # Get filters from request
    status_filter = request.args.get('status', type=str)
    disease_filter = _query_int("disease")
    hospital_filter = _query_int("hospital")
    lab_unit_filter = _query_int("lab_unit")  # Changed to use lab_unit ID
    search_query = request.args.get('search', type=str)
    
    with get_db_session() as db:
        # Get user's lab unit IDs for scoping
        user_lab_unit_ids = {
            lab_unit.id
            for lab_unit in clinical_lab_units(
                db, db.query(LabUnit), current_user
            ).all()
        }
        
        # Security check: Ensure requested filters are within user's scope
        if hospital_filter:
             h_query = select(Hospital).where(Hospital.id == hospital_filter)
             h_query = clinical_hospitals(db, h_query, current_user)
             if not db.execute(h_query).scalar_one_or_none():
                 abort(403, description="Unauthorized hospital filter")
        
        if lab_unit_filter:
             lu_query = select(LabUnit).where(LabUnit.id == lab_unit_filter)
             lu_query = clinical_lab_units(db, lu_query, current_user)
             if not db.execute(lu_query).scalar_one_or_none():
                 abort(403, description="Unauthorized lab unit filter")
        
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
        
        # Get hospitals and lab units for filters
        h_query = select(Hospital).order_by(Hospital.name.asc())
        h_query = clinical_hospitals(db, h_query, current_user)
        hospitals = db.execute(h_query).scalars().all()
        
        lu_query = select(LabUnit).order_by(LabUnit.name.asc())
        lu_query = clinical_lab_units(db, lu_query, current_user)
        lab_units = db.execute(lu_query).scalars().all()
        
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
