"""Results blueprint initialization."""

from flask import Blueprint

bp = Blueprint("analytics", __name__, url_prefix="/analytics")

from . import (
    route_direct_view,
    route_encounter_view,
    route_routes_simple,
    route_image_results,
    route_encounter_results,
    route_images_without_tasks
)  # noqa: E402,F401
