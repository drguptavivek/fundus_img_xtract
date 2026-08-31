"""Session-auth refresh of one EncounterSet's assets from its upstream source.

The mobile field surface has its own bearer-token route; this is the same
operation for the browser's encounter-set details panel, so both share one
service and cannot drift.
"""
from __future__ import annotations

import logging

from flask import jsonify, request
from flask_login import current_user, login_required

from db_transaction_manager import transaction_scope
from field_workbench import service as field_service
from field_workbench.exceptions import FieldError
from field_workbench.throttle import enforce_fetch_spacing

from . import api_bp

logger = logging.getLogger("api.field_encounter_refresh")


@api_bp.route("/encounter-sets/<uuid>/refresh-source", methods=["POST"])
@login_required
def refresh_encounter_source(uuid: str):
    """Re-query the upstream source for this encounter.

    Shares the field surface's per-user spacing guard: this reaches an external
    provider, so a details panel must not become a way around the throttle.
    """
    try:
        with transaction_scope() as db:
            enforce_fetch_spacing(current_user.id)
            result = field_service.refresh_encounter_from_source(
                db,
                user=current_user,
                encounter_uuid=uuid,
                remote_addr=request.remote_addr,
            )
        return jsonify({"success": True, "data": result})
    except FieldError as exc:
        response = jsonify({"success": False, "error": exc.code, "message": exc.message})
        response.status_code = exc.status_code
        retry_after = getattr(exc, "retry_after", None)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response
