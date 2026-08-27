"""Explicit endpoint contracts for vertical-slice migration."""

from authz_v2.core.actions import Action

from .contracts import EndpointMode, EndpointPolicy


def _screen(action: Action = Action.TASKS_VIEW) -> EndpointPolicy:
    return EndpointPolicy(EndpointMode.SCREEN, action, enforcement="screen_entry")


def _exact(action: Action, resolver: str) -> EndpointPolicy:
    return EndpointPolicy(EndpointMode.PROTECTED, action, resolver=resolver)


def _grading_slot(binding: str) -> EndpointPolicy:
    return EndpointPolicy(
        EndpointMode.PROTECTED,
        Action.GRADING_RESIDENT_SUBMIT,
        action_variants=(
            Action.GRADING_RESIDENT2_SUBMIT,
            Action.GRADING_ARBITRATOR_SUBMIT,
        ),
        binding=binding,
    )


ROUTE_POLICIES: dict[str, EndpointPolicy] = {
    # Grading dashboard and queue selection only admit the screen. Row/task
    # authorization remains exact through the action-specific queue policies.
    "grading.index": _screen(),
    "grading.disease_queue_fragment": _screen(),
    "grading.disease_queues_fragment": _screen(),
    "grading.project_queues_fragment": _screen(),
    "grading.refresh_queues_trigger": _screen(),
    "grading.start_grading": _screen(),
    "grading.linked_followup": _screen(),
    # Slot-bearing task opens/submissions select one of the three declared
    # grading actions only after resolving the stored task and requested slot.
    "grading.dual_grading_task": _grading_slot("grading_slot_task"),
    "grading.dual_grading_submit": _grading_slot("grading_slot_submission"),
    "grading.encounter_set_package_grading": _grading_slot("grading_package_task"),
    "grading.encounter_set_package_submit": _grading_slot("grading_package_submission"),
    "grading.revise_grading": _exact(Action.GRADING_GRADES_VIEW, "grading_task"),
    "grading.dual_grading_feature_geometry": _exact(
        Action.GRADING_GRADES_VIEW, "grading_task"
    ),
    "grading.intra_rater_task": _exact(
        Action.INTRA_RATER_TASK_VIEW, "intra_rater_task"
    ),
    "grading.intra_rater_feature_geometry": _exact(
        Action.INTRA_RATER_TASK_VIEW, "intra_rater_task"
    ),
    "grading.intra_rater_submit": _exact(
        Action.INTRA_RATER_TASK_SUBMIT, "intra_rater_task"
    ),
    "grading.regrade_tasks": _screen(),
    "grading.regrade_tasks_reassign": _screen(),
    "grading.start_random_regrade_task": _screen(),
    "grading.regrade_task_detail": _exact(Action.REVIEW_TASK_VIEW, "grading_task"),
    "grading.regrade_task_submit": _exact(
        Action.REVIEW_REGRADE_ADJUDICATE, "grading_task"
    ),
    "grading.regrade_task_reassign": _exact(
        Action.REVIEW_REGRADE_CREATOR_MANAGE, "grading_task"
    ),
    "grading.wadhwani_glaucoma_inference_page": _screen(Action.INFERENCE_WAI_SUMMARY),
    "grading.wadhwani_glaucoma_inference_run": _exact(
        Action.INFERENCE_WAI_RUN, "inference_target"
    ),
    "grading.wadhwani_glaucoma_inference_job_page": _exact(
        Action.JOBS_RESULT_VIEW, "job"
    ),
    "grading.wadhwani_glaucoma_inference_job_status_partial": _exact(
        Action.JOBS_RESULT_VIEW, "job"
    ),
    "grading.workbench_page": _screen(),
    "grading.grader_statistics": _screen(),
    "grading.inter_rater_compare": _screen(),
    "grading.inter_rater_viewer": _exact(Action.MEDIA_IMAGE_VIEW, "image"),
}


def catalogued_endpoint_policy(endpoint: str | None) -> EndpointPolicy | None:
    return ROUTE_POLICIES.get(endpoint) if endpoint else None
