"""Routes for encounter files dataframe display."""

from __future__ import annotations

import math

from flask import current_app, render_template, request, url_for, flash, redirect
from flask_login import current_user
from auth.roles import roles_required
from db_transaction_manager import get_db_session

from . import bp
from api.kpis.encounter_files_kpis import get_filtered_encounter_dataframe
from api.kpis.kpiutils import parse_filter_params, get_user_permissions
from analytics.utils import build_pagination_params
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.date_utils import parse_date_yyyy_mm_dd


@bp.route("/encounter-files", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "analytics_viewer",
    "optometrist",
)
def encounter_files() -> str:
    """Render encounter files dataframe with filtering and pagination."""
    
    page = request.args.get("page", default=1, type=int) or 1
    start_date_str = (request.args.get("start_date") or "").strip() or None
    end_date_str = (request.args.get("end_date") or "").strip() or None
    
    # Parse date filters
    start_date = parse_date_yyyy_mm_dd(start_date_str)
    end_date = parse_date_yyyy_mm_dd(end_date_str)
    
    page = max(1, page)
    per_page = current_app.config.get("REPORT_ENCOUNTER_FILES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    # Use the API module to get filtered dataframe
    with get_db_session() as db:
        # Parse filter parameters using API utility
        params = parse_filter_params()
        
        # Override date filters if they were provided in the request
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
            
        # Get user permissions using API utility (already no admin override)
        user_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
        if not user_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))
        
        # Get filtered dataframe using API function
        df, _ = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
    
    # Get total count after filtering
    total = len(df)
    
    # Apply pagination
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    df_page = df.iloc[start_idx:end_idx]
    
    # Convert dataframe to list of dictionaries for template
    encounter_data = df_page.to_dict('records')
    
    # Convert dataframe to HTML for display
    df_html = df_page.to_html(
        classes='table table-striped table-hover table-sm',
        table_id='encounter-files-table',
        index=False,
        escape=False,
        na_rep='-'
    )

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
        "start_date": start_date_str,
        "end_date": end_date_str,
    }

    prev_url = (
        url_for("analytics.encounter_files", **build_pagination_params(filter_params, page - 1))
        if page > 1
        else None
    )
    next_url = (
        url_for("analytics.encounter_files", **build_pagination_params(filter_params, page + 1))
        if page < total_pages
        else None
    )

    return render_template(
        "analytics/encounter_files_kpi_display.html",
        encounter_data=encounter_data,
        df_html=df_html,
        filters=filter_params,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        total=total,
        per_page=per_page,
    )
