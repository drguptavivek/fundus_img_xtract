"""Results blueprint initialization."""

from flask import Blueprint

bp = Blueprint("analytics", __name__, url_prefix="/analytics")

from . import routes, direct_view, encounter_view, routes_simple  # noqa: E402,F401
