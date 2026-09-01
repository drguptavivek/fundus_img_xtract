"""Public KPI API for mobile, JavaScript, and HTMX clients."""

from __future__ import annotations

from flask import current_app, jsonify, render_template, request

from analytics.public_kpis import get_public_kpis
from analytics.public_kpis.service import PUBLIC_KPI_CACHE_SECONDS
from utils.log_sanitize import sanitize_log_value
from utils.rate_limiter import rate_limit

from . import api_bp


@api_bp.get("/public_kpis")
@rate_limit("120 per minute", methods=["GET"])
def public_kpis():
    """Return privacy-safe system aggregates as JSON or an HTMX fragment."""

    try:
        kpis = get_public_kpis()
    except Exception as exc:  # noqa: BLE001 - keep the public API fail-safe
        current_app.logger.error(
            "Unable to load public KPIs: %s",
            sanitize_log_value(exc),
        )
        return jsonify({"success": False, "error": "Public KPIs are temporarily unavailable."}), 500
    if request.headers.get("HX-Request", "").lower() == "true":
        return render_template("public/_kpi_cards.html", kpis=kpis)

    return jsonify(
        {
            "success": True,
            "data": kpis.to_dict(),
            "meta": {"cache_ttl_seconds": PUBLIC_KPI_CACHE_SECONDS},
        }
    )
