from flask import Blueprint

bp = Blueprint("dual_grading", __name__, url_prefix="/dual_grading")

# Import all route handlers
from .dashboard import index
from .analysis import paired_gradings, discrepancy_analysis
from grading.matching import matching_dashboard, run_matching_process

# Register routes with the blueprint
bp.add_url_rule("/", view_func=index, methods=["GET"])
bp.add_url_rule("/paired_gradings", view_func=paired_gradings, methods=["GET"])
bp.add_url_rule("/discrepancy_analysis", view_func=discrepancy_analysis, methods=["GET"])
bp.add_url_rule("/matching", view_func=matching_dashboard, methods=["GET"])
bp.add_url_rule("/matching/run", view_func=run_matching_process, methods=["POST"])