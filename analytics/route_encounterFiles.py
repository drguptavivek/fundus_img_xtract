"""Routes for encounter files dataframe display."""

from __future__ import annotations

import math
from datetime import datetime, date as _date
from typing import Any

from flask import current_app, render_template, request, url_for
from flask_login import current_user
from auth.roles import roles_required
from sqlalchemy.orm import selectinload

from . import bp
from models import (
    Hospital,
    LabUnit,
    PatientEncounters,
    Session,
)
from utils.dataframeEncounterFiles import generate_encounter_upload_metrics_df
from utils.upload_eligibility import get_user_lab_unit_ids


def _parse_date(value: str | None) -> _date | None:
    """Parse date string from form input."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/encounter-files", methods=["GET"])
@roles_required("admin", "data_manager")
def encounter_files() -> str:
    """Render encounter files dataframe with filtering and pagination."""
    
    page = request.args.get("page", default=1, type=int) or 1
    hospital_id = request.args.get("hospital_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    start_date_str = (request.args.get("start_date") or "").strip() or None
    end_date_str = (request.args.get("end_date") or "").strip() or None
    
    # Parse date filters
    start_date = _parse_date(start_date_str)
    end_date = _parse_date(end_date_str)
    
    page = max(1, page)
    per_page = current_app.config.get("REPORT_ENCOUNTER_FILES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    # Check user permissions for lab unit access
    user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    is_admin_like = current_user.has_role("admin", "data_manager")
    
    # Generate dataframe using the utility function with manual session handling
    from utils.utils import with_session
    
    # Create a simple wrapper that handles the session correctly
    def get_dataframe():
        db = Session()
        try:
            return generate_encounter_upload_metrics_df(
                        db=db,
                        start_date=start_date,
                        end_date=end_date
                    )
        finally:
            db.close()
    
    df = get_dataframe()
    
    # Apply lab unit access control to dataframe
    if not is_admin_like and user_lab_unit_ids:
        df = df[df['lab_unit_id'].isin(user_lab_unit_ids)]
    
    # Apply additional filters
    if hospital_id:
        df = df[df['hospital_id'] == hospital_id]
        
    if lab_unit_id:
        # Only allow filtering by lab_unit_id if user has access to that lab unit
        if not is_admin_like and lab_unit_id not in user_lab_unit_ids:
            from flask import abort
            abort(403, description="Access denied to this lab unit")
        df = df[df['lab_unit_id'] == lab_unit_id]
    
    # Get total count after filtering
    total = len(df)
    
    # Apply pagination
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    df_page = df.iloc[start_idx:end_idx]
    
    # Convert dataframe to list of dictionaries for template
    encounter_data = df_page.to_dict('records')
    
    # Now get hospitals and lab units for filters
    db = Session()
    try:
        # Filter hospitals and lab units to only those user has access to
        if is_admin_like:
            hospitals = db.query(Hospital).order_by(Hospital.name).all()
            lab_units = db.query(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name).all()
        else:
            lab_units = (
                db.query(LabUnit)
                .filter(LabUnit.id.in_(list(user_lab_unit_ids)))
                .options(selectinload(LabUnit.hospital))
                .order_by(LabUnit.name)
                .all()
            )
            # Get hospitals for allowed lab units
            hospital_ids = [lu.hospital_id for lu in lab_units]
            hospitals = (
                db.query(Hospital)
                .filter(Hospital.id.in_(hospital_ids))
                .order_by(Hospital.name)
                .all()
            )
        
        # Convert dataframe to HTML for display
        df_html = df_page.to_html(
            classes='table table-striped table-hover table-sm',
            table_id='encounter-files-table',
            index=False,
            escape=False,
            na_rep='-'
        )
        
    finally:
        db.close()

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "start_date": start_date_str,
        "end_date": end_date_str,
    }

    def _filter_kwargs(target_page: int) -> dict[str, int | str]:
        params: dict[str, int | str] = {"page": target_page}
        for key, value in filter_params.items():
            if not value:
                continue
            params[key] = value
        return params

    prev_url = url_for("analytics.encounter_files", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("analytics.encounter_files", **_filter_kwargs(page + 1)) if page < total_pages else None

    return render_template(
        "analytics/encounter_files.html",
        encounter_data=encounter_data,
        df_html=df_html,
        hospitals=hospitals,
        lab_units=lab_units,
        filters=filter_params,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        total=total,
        per_page=per_page,
    )