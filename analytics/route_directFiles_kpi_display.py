"""Routes for direct files dataframe display."""

from __future__ import annotations

import math
from datetime import date as _date, datetime
from typing import Any, Dict, List, Tuple

from flask import current_app, render_template, request, url_for
from flask_login import current_user
from auth.roles import roles_required
from app_cache import cache
from db_transaction_manager import get_db_session

from . import bp
from api.kpis.direct_files_kpis import get_filtered_direct_image_dataframe
from api.kpis.kpiutils import parse_filter_params, get_user_permissions
from analytics.utils import build_pagination_params
from utils.date_utils import parse_date_yyyy_mm_dd

DISPLAY_COLUMNS: Tuple[str, ...] = (
    "image_uuid",
    "upload_date",
    "upload_datetime",
    "hospital_name",
    "lab_unit_name",
    "camera_name",
    "disease_name",
    "is_mydriatic",
    "is_pregraded",
    "verification_status",
    "verified_by_username",
    "verified_at",
    "task_count",
    "grading_count",
    "latest_task_date",
    "latest_grading_date",
)


@bp.route("/direct-files", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def direct_files() -> str:
    """Render direct files dataframe with filtering and pagination."""
    
    page = request.args.get("page", default=1, type=int) or 1
    start_date_str = (request.args.get("start_date") or "").strip() or None
    end_date_str = (request.args.get("end_date") or "").strip() or None
    
    # Parse date filters
    start_date = parse_date_yyyy_mm_dd(start_date_str)
    end_date = parse_date_yyyy_mm_dd(end_date_str)
    
    page = max(1, page)
    per_page = current_app.config.get("REPORT_DIRECT_FILES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    # Parse filters and permissions
    params = parse_filter_params()
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    user_lab_unit_ids = get_user_permissions(current_user.id)

    # Build deterministic key for caching
    params_key = _build_params_key(params)

    # Cached fetch for this user + filters + page
    df_html, direct_files_data, total = _get_direct_files_page(
        current_user.id,
        params_key,
        params,
        tuple(sorted(user_lab_unit_ids)),
        page,
        per_page,
    )

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
        "start_date": start_date_str,
        "end_date": end_date_str,
    }

    prev_url = (
        url_for("analytics.direct_files", **build_pagination_params(filter_params, page - 1))
        if page > 1
        else None
    )
    next_url = (
        url_for("analytics.direct_files", **build_pagination_params(filter_params, page + 1))
        if page < total_pages
        else None
    )

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


_CACHE_TIMEOUT = 15 * 60  # 15 minutes


@cache.memoize(timeout=_CACHE_TIMEOUT)
def _get_direct_files_page(
    user_id: int,
    params_key: Tuple[Tuple[str, str], ...],
    params: Dict[str, Any],
    user_lab_unit_ids: Tuple[int, ...],
    page: int,
    per_page: int,
) -> Tuple[str, List[Dict[str, Any]], int]:
    """Return cached HTML/table data for direct files list for a user and filter set."""
    with get_db_session() as db:
        df, _ = get_filtered_direct_image_dataframe(db, params, list(user_lab_unit_ids))

    total = len(df)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    df_page = df.iloc[start_idx:end_idx]
    for col in DISPLAY_COLUMNS:
        if col not in df_page.columns:
            df_page[col] = None
    df_page = df_page[list(DISPLAY_COLUMNS)]

    direct_files_data = df_page.to_dict("records")
    df_html = df_page.to_html(
        classes="table table-striped table-hover table-sm",
        table_id="direct-files-table",
        index=False,
        escape=False,
        na_rep="-",
    )
    return df_html, direct_files_data, total


def _build_params_key(params: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
    """Normalize params into a deterministic, hashable key for caching."""
    normalized: List[Tuple[str, str]] = []
    for key, value in sorted(params.items()):
        if isinstance(value, (_date, datetime)):
            normalized.append((key, value.isoformat()))
        else:
            normalized.append((key, str(value)))
    return tuple(normalized)
