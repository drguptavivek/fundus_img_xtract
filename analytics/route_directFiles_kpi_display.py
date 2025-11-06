"""Routes for direct files dataframe display."""

from __future__ import annotations

import math
from datetime import datetime, date as _date
from typing import Any

from flask import current_app, render_template, request, url_for
from flask_login import current_user
from auth.roles import roles_required

from . import bp
from api.kpis.direct_files_kpis import get_filtered_direct_image_dataframe
from api.kpis.kpiutils import parse_filter_params, get_user_permissions


def _parse_date(value: str | None) -> _date | None:
    """Parse date string from form input."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/direct-files", methods=["GET"])
@roles_required("admin", "data_manager")
def direct_files() -> str:
    """Render direct files dataframe with filtering and pagination."""
    
    page = request.args.get("page", default=1, type=int) or 1
    start_date_str = (request.args.get("start_date") or "").strip() or None
    end_date_str = (request.args.get("end_date") or "").strip() or None
    
    # Parse date filters
    start_date = _parse_date(start_date_str)
    end_date = _parse_date(end_date_str)
    
    page = max(1, page)
    per_page = current_app.config.get("REPORT_DIRECT_FILES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    # Use the API module to get filtered dataframe
    from db_transaction_manager import get_db_session
    
    with with_session() as db:
        # Parse filter parameters using API utility
        params = parse_filter_params()
        
        # Override date filters if they were provided in the request
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
            
        # Get user permissions using API utility
        user_lab_unit_ids = get_user_permissions(current_user.id)
        
        # Get filtered dataframe using API function
        df, _ = get_filtered_direct_image_dataframe(db, params, user_lab_unit_ids)
    
    # Get total count after filtering
    total = len(df)
    
    # Apply pagination
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    df_page = df.iloc[start_idx:end_idx]
    
    # Convert dataframe to list of dictionaries for template
    direct_files_data = df_page.to_dict('records')
    
    # Convert dataframe to HTML for display
    df_html = df_page.to_html(
        classes='table table-striped table-hover table-sm',
        table_id='direct-files-table',
        index=False,
        escape=False,
        na_rep='-'
    )

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
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

    prev_url = url_for("analytics.direct_files", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("analytics.direct_files", **_filter_kwargs(page + 1)) if page < total_pages else None

    return render_template(
        "analytics/direct_files_kpi_display.html",
        direct_files_data=direct_files_data,
        df_html=df_html,
        filters=filter_params,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        total=total,
        per_page=per_page,
    )