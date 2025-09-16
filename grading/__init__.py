from flask import Blueprint

bp = Blueprint("grading", __name__, url_prefix="/grading")

# Import all route handlers
from .dashboard import index
from .dual_grading import dual_grading_task, dual_grading_submit, revise_grading
from .start_grading import start_grading

# Register routes with the blueprint
bp.add_url_rule("/", view_func=index, methods=["GET"])

# Dual grading routes
bp.add_url_rule("/task/<int:task_id>", view_func=dual_grading_task, methods=["GET"])
bp.add_url_rule("/task/submit", view_func=dual_grading_submit, methods=["POST"])
bp.add_url_rule("/revise/<int:grade_id>", view_func=revise_grading, methods=["GET"])

# Start grading route
bp.add_url_rule("/grade/<int:disease_id>/<string:role_slot>", view_func=start_grading, methods=["GET"])

