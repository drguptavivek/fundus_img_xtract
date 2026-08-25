"""
Dual Grading System Blueprint

This blueprint provides the complete dual grading workflow for retinal fundus images,
including three-tier grading (resident → resident2 → arbitrator), consensus management,
and comprehensive task tracking.


Module Structure:
- dashboard.py: Main dashboard with KPIs and grading history
- dual_grading.py: Core grading workflow with task access, submission, and revision
- start_grading.py: Entry point for initiating grading sessions
- encounter_set_grading.py: Encounter-set based grading for diseases like Strabismus
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
- /encounter_set/<uuid>: Grade encounter set with sync-grid viewer
"""

from flask import Blueprint

bp = Blueprint("grading", __name__, url_prefix="/grading")

_routes_configured = False


def configure_blueprint() -> Blueprint:
    """Register routes lazily so ORM model discovery cannot import Flask routes."""
    global _routes_configured
    if _routes_configured:
        return bp

    from .dashboard import (
        index,
        disease_queue_fragment,
        disease_queues_fragment,
        project_queues_fragment,
        refresh_queues_trigger,
    )
    from .dual_grading import register_routes as register_dual_grading_routes
    from .start_grading import register_routes as register_start_grading_routes
    from .intra_rater import register_routes as register_intra_rater_routes
    from .inter_rater_compare import register_routes as register_inter_rater_routes
    from .grader_statistics import register_routes as register_grader_statistics_routes
    from .encounter_set_grading import register_routes as register_encounter_set_routes
    from .encounter_set_package_grading import register_routes as register_encounter_set_package_routes
    from .regrade_tasks import register_routes as register_regrade_task_routes
    from .wadhwani_glaucoma_inference import register_routes as register_wadhwani_glaucoma_inference_routes
    from .workbench_page import register_routes as register_workbench_page_routes

    bp.add_url_rule("/", view_func=index, methods=["GET"])
    bp.add_url_rule(
        "/fragments/disease-queue/<int:disease_id>",
        view_func=disease_queue_fragment,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/fragments/disease-queues",
        view_func=disease_queues_fragment,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/fragments/project-queues",
        view_func=project_queues_fragment,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/fragments/refresh-queues",
        view_func=refresh_queues_trigger,
        methods=["GET"],
    )
    register_dual_grading_routes(bp)
    register_start_grading_routes(bp)
    register_intra_rater_routes(bp)
    register_inter_rater_routes(bp)
    register_grader_statistics_routes(bp)
    register_encounter_set_routes(bp)
    register_encounter_set_package_routes(bp)
    register_regrade_task_routes(bp)
    register_wadhwani_glaucoma_inference_routes(bp)
    register_workbench_page_routes(bp)
    _routes_configured = True
    return bp
