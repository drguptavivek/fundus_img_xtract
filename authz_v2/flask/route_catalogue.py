"""Explicit endpoint contracts for vertical-slice migration."""

from authz_v2.core.actions import Action

from .contracts import EndpointMode, EndpointPolicy


def _screen(action: Action = Action.TASKS_VIEW) -> EndpointPolicy:
    return EndpointPolicy(EndpointMode.SCREEN, action, enforcement="screen_entry")


def _exact(action: Action, resolver: str) -> EndpointPolicy:
    return EndpointPolicy(EndpointMode.PROTECTED, action, resolver=resolver)


def _mobile(action: Action, resolver: str) -> EndpointPolicy:
    return EndpointPolicy(EndpointMode.MOBILE_SESSION, action, resolver=resolver)


def _mobile_entry(action: Action) -> EndpointPolicy:
    return EndpointPolicy(EndpointMode.MOBILE_SESSION, action)


def _signed(action: Action, resolver: str) -> EndpointPolicy:
    return EndpointPolicy(EndpointMode.SIGNED_RESOURCE, action, resolver=resolver)


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
    # Mobile authentication keeps public credential issuance distinct from
    # refresh-token rotation/revocation. The signed resolver must derive the
    # exact stored session from the presented refresh token.
    "mobile_api.login": EndpointPolicy(EndpointMode.PUBLIC, Action.AUTH_LOGIN),
    "mobile_api.refresh": _signed(Action.AUTH_MOBILE_REFRESH, "mobile_session"),
    "mobile_api.logout": _signed(Action.AUTH_MOBILE_LOGOUT, "mobile_session"),
    # Access-token mobile session and self-service surfaces.
    "mobile_api.get_mobile_context": _mobile(Action.MOBILE_CONTEXT_VIEW, "user"),
    "mobile_api.get_mobile_upload_options": _mobile(
        Action.MOBILE_UPLOAD_OPTIONS_VIEW, "user"
    ),
    "mobile_api.list_user_sessions": _mobile(Action.MOBILE_SESSION_LIST, "user"),
    "mobile_api.get_user_session": _mobile(
        Action.MOBILE_SESSION_DETAIL_VIEW, "mobile_session"
    ),
    "mobile_api.revoke_user_session": _mobile(
        Action.MOBILE_SESSION_REVOKE, "mobile_session"
    ),
    # Field lists admit only a mobile-channel project screen. Every project,
    # encounter and related media operation below resolves exact stored scope.
    "mobile_api.field_projects": _mobile_entry(Action.MOBILE_FIELD_PROJECTS_LIST),
    **{
        endpoint: _mobile(Action.MOBILE_FIELD_PROJECT_VIEW, "project")
        for endpoint in (
            "mobile_api.field_encounter_dates",
            "mobile_api.field_encounters",
            "mobile_api.field_fetch_status",
        )
    },
    **{
        endpoint: _mobile(Action.MOBILE_FIELD_PROJECT_SYNC, "project")
        for endpoint in (
            "mobile_api.field_queue_fetch",
            "mobile_api.field_retry_fetch",
            "mobile_api.field_refetch_patient",
        )
    },
    **{
        endpoint: _mobile(Action.MOBILE_FIELD_ENCOUNTER_VIEW, "encounter")
        for endpoint in (
            "mobile_api.field_encounter_detail",
            "mobile_api.field_encounter_image",
            "mobile_api.field_encounter_image_thumbnail",
            "mobile_api.field_encounter_report",
        )
    },
    "mobile_api.field_request_inference": _mobile(
        Action.MOBILE_FIELD_INFERENCE_RUN, "encounter"
    ),
    "mobile_api.field_refresh_encounter": _mobile(
        Action.MOBILE_FIELD_ENCOUNTER_CAPTURE, "encounter"
    ),
    # Mobile upload creation resolves the project-site/profile tuple from the
    # submitted form. Follow-up routes resolve the caller-owned persisted job;
    # image UUID validation remains an application lineage check within it.
    "mobile_api.create_upload": _mobile(
        Action.MOBILE_UPLOAD_CREATE, "project_upload_target"
    ),
    **{
        endpoint: _mobile(Action.MOBILE_UPLOAD_VIEW, "job")
        for endpoint in (
            "mobile_api.upload_status",
            "mobile_api.upload_status_by_idempotency_key",
            "mobile_api.upload_inference",
            "mobile_api.upload_image_thumbnail",
        )
    },
    "mobile_api.retry_upload_inference": _mobile(
        Action.MOBILE_UPLOAD_INFERENCE_RETRY, "job"
    ),
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
    # Encounter-set verification.
    "verify_encounter_set.index": _screen(Action.PREPROCESS_DASHBOARD_VIEW),
    "verify_encounter_set.verify_encounter": _exact(
        Action.VERIFICATION_ENCOUNTER_SET_VIEW, "encounter"
    ),
    "verify_encounter_set.verify_panel": _exact(
        Action.VERIFICATION_ENCOUNTER_SET_VIEW, "encounter"
    ),
    "verify_encounter_set.edit_image": _exact(Action.MEDIA_IMAGE_VIEW, "image"),
    "verify_encounter_set.save_edit": _exact(Action.PREPROCESS_IMAGE_UPDATE, "image"),
    "verify_encounter_set.mark_anonymized": _exact(
        Action.PREPROCESS_IMAGE_UPDATE, "image"
    ),
    "verify_encounter_set.mark_all_anonymized": _exact(
        Action.VERIFICATION_ENCOUNTER_SET_UPDATE, "encounter"
    ),
    "verify_encounter_set.restore_original": _exact(
        Action.PREPROCESS_IMAGE_UPDATE, "image"
    ),
    "verify_encounter_set.mark_not_gradable": _exact(
        Action.PREPROCESS_IMAGE_UPDATE, "image"
    ),
    "verify_encounter_set.undo_not_gradable": _exact(
        Action.PREPROCESS_IMAGE_UPDATE, "image"
    ),
    **{
        endpoint: _exact(Action.VERIFICATION_ENCOUNTER_SET_UPDATE, "encounter")
        for endpoint in (
            "verify_encounter_set.update_metadata",
            "verify_encounter_set.update_position",
            "verify_encounter_set.mark_reviewed",
            "verify_encounter_set.exclude_encounter_set",
            "verify_encounter_set.reopen_verification",
            "verify_encounter_set.finalize_verification",
        )
    },
    # Remidio encounter verification.
    "verify_remedio.verify_index": _screen(Action.PREPROCESS_DASHBOARD_VIEW),
    "verify_remedio.verify_list": _screen(Action.PREPROCESS_DASHBOARD_VIEW),
    "verify_remedio.kpi_trend": _screen(Action.PREPROCESS_DASHBOARD_VIEW),
    **{
        endpoint: _exact(Action.VERIFICATION_REMIDIO_VIEW, "encounter")
        for endpoint in (
            "verify_remedio.verify_detail",
            "verify_remedio.verify_edit",
            "verify_remedio.viewer_panel",
        )
    },
    **{
        endpoint: _exact(Action.VERIFICATION_REMIDIO_UPDATE, "encounter")
        for endpoint in (
            "verify_remedio.verify_save",
            "verify_remedio.mark_eye",
            "verify_remedio.verify_dr",
            "verify_remedio.unverify_dr",
            "verify_remedio.verify_glaucoma",
            "verify_remedio.unverify_glaucoma",
            "verify_remedio.verify_encounter",
            "verify_remedio.unverify_encounter",
        )
    },
}


def catalogued_endpoint_policy(endpoint: str | None) -> EndpointPolicy | None:
    return ROUTE_POLICIES.get(endpoint) if endpoint else None
