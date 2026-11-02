"""Admin-only security incident and deployed mitigation overview."""
import redis
from flask import current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from security_incidents.service import security_overview
from utils.rate_limiter import rate_limit
from . import api_bp


def _unavailable():
    response = jsonify({"error": "security_backend_unavailable", "message": "IP block state is unavailable."})
    response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    response.headers["Retry-After"] = "60"
    return response


@api_bp.get("/admin/security/incidents")
@login_required
@roles_required("admin")
@rate_limit("30 per minute")
def security_incident_overview():
    backend = current_app.extensions.get("api_abuse_backend")
    if backend is None:
        return _unavailable()
    try:
        with transaction_scope() as db:
            overview = security_overview(db, admin=current_user, backend=backend)
    except redis.RedisError:
        return _unavailable()
    if request.headers.get("HX-Request") == "true":
        response = current_app.make_response(render_template("admin/_security_incidents_workspace.html", overview=overview))
    else:
        response = jsonify(overview.to_dict())
    response.headers["Cache-Control"] = "no-store"
    response.vary.add("HX-Request")
    return response
