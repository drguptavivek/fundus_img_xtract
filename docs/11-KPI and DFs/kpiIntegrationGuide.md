
# KPI Integration Guide

## Overview

This guide demonstrates how to integrate analytics routes with the centralized KPI API system, using the patterns established in `analytics/route_encounterFiles_kpi_display.py` and `static/js/common-filters.js`.

## 🏗️ Architecture Pattern

### 1. Analytics Route Integration

When creating analytics routes that need to display filtered data with pagination, follow this pattern:

```python
"""Routes for analytics dataframe display."""

from __future__ import annotations

import math
from datetime import datetime, date as _date
from typing import Any

from flask import current_app, render_template, request, url_for
from flask_login import current_user
from auth.roles import roles_required

from . import bp
from api.kpis.encounter_files_kpis import get_filtered_encounter_dataframe
from api.kpis.kpiutils import parse_filter_params, get_user_permissions
from utils.utils import with_session


def _parse_date(value: str | None) -> _date | None:
    """Parse date string from form input."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/your-analytics-route", methods=["GET"])
@roles_required("admin", "data_manager")
def your_analytics_route() -> str:
    """Render analytics dataframe with filtering and pagination."""
    
    # Get pagination parameters
    page = request.args.get("page", default=1, type=int) or 1
    start_date_str = (request.args.get("start_date") or "").strip() or None
    end_date_str = (request.args.get("end_date") or "").strip() or None
    
    # Parse date filters
    start_date = _parse_date(start_date_str)
    end_date = _parse_date(end_date_str)
    
    page = max(1, page)
    per_page = current_app.config.get("REPORT_PAGE_SIZE", 50)
