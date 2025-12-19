"""
Dual Grading System Blueprint

This blueprint provides the complete dual grading workflow for retinal fundus images,
including three-tier grading (resident → resident2 → arbitrator), consensus management,
and comprehensive task tracking.


Module Structure:
- dashboard.py: Main dashboard with KPIs and grading history
- dual_grading.py: Core grading workflow with task access, submission, and revision
- start_grading.py: Entry point for initiating grading sessions
- consensus.py: Consensus management utilities wrapper

Documentation:
- flowdiagram.md: System architecture and process flows
- dual_grading_flow.md: Detailed logic and revision flows
- dual_grading_utils.md: Comprehensive function documentation
- edge_cases.md: Edge case analysis and resolution status
- errors.md: Recent error fixes and resolutions
- module_integration_guide.md: Module interaction guide

Routes:
- /: Dashboard with KPIs and grading history
- /grade/<disease_id>/<role_slot>: Start grading for specific disease/role
- /task/<task_id>/<slot_type>: Access/review specific grading task
- /task/submit: Submit grade for a task
- /revise/<grade_id>: Revise an existing grade
"""

from flask import Blueprint

bp = Blueprint("grading", __name__, url_prefix="/grading")

# Import all route handlers
from .dashboard import index
from .dual_grading import register_routes as register_dual_grading_routes
from .start_grading import register_routes as register_start_grading_routes
from .intra_rater import register_routes as register_intra_rater_routes
from .inter_rater_compare import register_routes as register_inter_rater_routes
from .grader_statistics import register_routes as register_grader_statistics_routes

# Register routes with the blueprint
bp.add_url_rule("/", view_func=index, methods=["GET"])

# Register dual grading routes
register_dual_grading_routes(bp)

# Register start grading routes
register_start_grading_routes(bp)

# Register intra-rater routes
register_intra_rater_routes(bp)

# Register inter-rater comparison routes
register_inter_rater_routes(bp)
register_grader_statistics_routes(bp)
