from flask import Blueprint

bp = Blueprint("grading", __name__, url_prefix="/grading")

# Import all route handlers
from .dashboard import index
from .dual_grading import register_routes as register_dual_grading_routes
from .start_grading import register_routes as register_start_grading_routes

# Register routes with the blueprint
bp.add_url_rule("/", view_func=index, methods=["GET"])

# Register dual grading routes
register_dual_grading_routes(bp)

# Register start grading routes
register_start_grading_routes(bp)

