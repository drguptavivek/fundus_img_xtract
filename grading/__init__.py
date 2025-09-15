from flask import Blueprint

bp = Blueprint("grading", __name__, url_prefix="/grading")

# Import all route handlers
from .dashboard import index
from .dual_grading import dual_grading_task, dual_grading_submit

# Register routes with the blueprint
bp.add_url_rule("/", view_func=index, methods=["GET"])

# Dual grading routes
bp.add_url_rule("/task/<int:task_id>", view_func=dual_grading_task, methods=["GET"])
bp.add_url_rule("/task/submit", view_func=dual_grading_submit, methods=["POST"])

