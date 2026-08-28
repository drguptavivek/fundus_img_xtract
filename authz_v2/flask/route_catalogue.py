"""Explicit endpoint contracts for vertical-slice migration."""

from authz_v2.core.actions import Action

from .contracts import EndpointMode, EndpointPolicy

EndpointPolicies = EndpointPolicy | dict[str, EndpointPolicy]


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


def _wai_project(binding: str) -> EndpointPolicy:
    return EndpointPolicy(
        EndpointMode.PROTECTED,
        Action.PROJECT_WAI_RUN,
        action_variants=(Action.INFERENCE_WAI_RUN,),
        binding=binding,
    )


ROUTE_POLICIES: dict[str, EndpointPolicies] = {
    **{
        endpoint: EndpointPolicy(EndpointMode.PUBLIC, Action.PUBLIC_VIEW)
        for endpoint in (
            "_favicon",
            "_robots",
            "_mobile_pwa_no_slash",
            "_mobile_android_apk_download",
            "_mobile_android_aab_download",
            "_mobile_pwa",
            "sitemap",
            "homepage",
            "home.index",
            "style_guide",
            "test_rate_limit",
            "healthz",
        )
    },
    **{
        endpoint: EndpointPolicy(EndpointMode.PUBLIC, Action.DOCS_API_VIEW)
        for endpoint in (
            "docs.api_docs",
            "docs.api_docs_html",
            "docs.openapi_spec",
            "docs.docs_index",
            "docs.swagger_ui",
            "docs.swagger_json",
        )
    },
    "help.index": EndpointPolicy(EndpointMode.PUBLIC, Action.HELP_VIEW),
    "help.view_document": EndpointPolicy(EndpointMode.PUBLIC, Action.HELP_VIEW),
    **{
        endpoint: _screen(Action.ANALYTICS_UPLOAD_STATS_VIEW)
        for endpoint in (
            "fundus_api.upload_stats_today",
            "fundus_api.upload_stats_last_7_days",
        )
    },
    **{
        endpoint: _screen(Action.DASHBOARD_VIEW)
        for endpoint in ("dashboard.hospital_dashboard", "dashboard.image_list")
    },
    "dashboard.hospital_detail": _exact(
        Action.DASHBOARD_HOSPITAL_VIEW, "lookup_record"
    ),
    "screenings.list_screenings": _screen(Action.SCREENINGS_LIST),
    "screenings.screening_detail": _exact(Action.SCREENINGS_VIEW, "encounter"),
    "screenings.reprocess_pdf": _exact(Action.SCREENINGS_REPROCESS, "encounter"),
    **{
        endpoint: _exact(Action.SCREENINGS_DELETE, "encounter")
        for endpoint in (
            "screenings.delete_encounter",
            "screenings.delete_reports",
        )
    },
    "reports.glaucoma_results_redirect": _screen(Action.REPORTS_LIST),
    **{
        endpoint: _exact(Action.REPORTS_VIEW, "report")
        for endpoint in (
            "reports.serve_dr_pdf_by_uuid",
            "reports.serve_glaucoma_pdf_by_uuid",
        )
    },
    "fundus_api.encounter_viewer_encounter": _exact(
        Action.ENCOUNTER_VIEWER_VIEW, "encounter"
    ),
    "fundus_api.encounter_viewer_image": _exact(Action.TASKS_VIEWER_VIEW, "image"),
    **{
        endpoint: _screen(Action.ANALYTICS_KPI_VIEW)
        for endpoint in (
            "analytics.direct_uploads_kpi",
            "analytics.encounter_files",
        )
    },
    **{
        endpoint: _screen(Action.ANALYTICS_ENCOUNTERS_VIEW)
        for endpoint in (
            "analytics.encounter_results_simple",
            "analytics.threshold_explorer",
        )
    },
    "analytics.wai_api_statistics": _screen(Action.INFERENCE_WAI_SUMMARY),
    "analytics.view_direct_image": _exact(
        Action.UPLOAD_DIRECT_VIEW, "direct_image_upload"
    ),
    "analytics.view_encounter": _exact(
        Action.ENCOUNTER_VIEWER_VIEW, "encounter"
    ),
    **{
        endpoint: _screen(Action.TASKS_VIEW)
        for endpoint in ("tasks.index", "tasks.pending")
    },
    "uploaded_zips.list_uploaded_zips": _screen(Action.UPLOAD_WORKSPACE_VIEW),
    "audit.missing_capture_date": _screen(Action.AUDIT_DATA_QUALITY_VIEW),
    "fundus_api.get_project_annotation_policy": _exact(
        Action.PROJECT_ANNOTATION_POLICY_VIEW, "project"
    ),
    "fundus_api.put_project_annotation_policy": _exact(
        Action.PROJECT_ANNOTATION_POLICY_MANAGE, "project"
    ),
    "fundus_api.export_project_schema": _exact(
        Action.PROJECT_ANNOTATION_POLICY_EXPORT, "project"
    ),
    **{
        endpoint: _exact(Action.AUTHORIZATION_ME_UPLOAD_OPTIONS_VIEW, "user")
        for endpoint in (
            "fundus_api.get_eligible_lab_units",
            "fundus_api.get_eligible_lab_units_currentUser",
        )
    },
    "account.profile": {
        "GET": _exact(Action.ACCOUNT_PROFILE_VIEW, "user"),
        "POST": _exact(Action.ACCOUNT_PROFILE_UPDATE, "user"),
    },
    **{
        endpoint: _exact(Action.ACCOUNT_PASSWORD_CHANGE, "user")
        for endpoint in (
            "account.change_password_self",
            "account.change_password_submit",
        )
    },
    "account.password_changed": _exact(Action.ACCOUNT_PROFILE_VIEW, "user"),
    **{
        endpoint: _screen(Action.PROJECT_REVIEW_LIST)
        for endpoint in ("projects.index", "fundus_api.review_projects")
    },
    **{
        endpoint: _exact(Action.PROJECT_REVIEW_VIEW, "project")
        for endpoint in (
            "projects.summary",
            "projects.uploads",
            "projects.gradings",
            "fundus_api.project_review_summary",
            "fundus_api.project_review_uploads",
            "fundus_api.project_review_gradings",
        )
    },
    **{
        endpoint: _exact(Action.ACCOUNT_VIEWER_PREFERENCES_MANAGE, "user")
        for endpoint in (
            "fundus_api.get_viewer_settings",
            "fundus_api.save_viewer_settings",
            "fundus_api.get_viewer_presets",
            "fundus_api.save_viewer_preset",
            "fundus_api.delete_viewer_preset",
        )
    },
    **{
        endpoint: _mobile_entry(Action.GLAUCOMA_AI_UPLOADS_LIST)
        for endpoint in (
            "fundus_api.list_recent_glaucoma_ai_uploads",
            "fundus_api.list_recent_glaucoma_ai_upload_results",
        )
    },
    **{
        endpoint: _mobile(
            Action.GLAUCOMA_AI_UPLOAD_VIEW, "direct_image_upload"
        )
        for endpoint in (
            "fundus_api.get_glaucoma_ai_upload_result",
            "fundus_api.get_glaucoma_ai_upload_image",
            "fundus_api.get_glaucoma_ai_upload_thumbnail",
        )
    },
    "fundus_api.create_glaucoma_ai_upload": _mobile(
        Action.GLAUCOMA_AI_MOBILE_UPLOAD_CREATE, "project_upload_target"
    ),
    "fundus_api.create_glaucoma_ai_upload_web": _exact(
        Action.GLAUCOMA_AI_UPLOAD_CREATE, "project_upload_target"
    ),
    **{
        endpoint: _screen(Action.UPLOAD_WORKSPACE_VIEW)
        for endpoint in (
            "glaucoma_ai.upload_form_partial",
            "glaucoma_ai.recent_results_partial",
            "glaucoma_ai.workspace_partial",
            "glaucoma_ai.recent_results_json",
        )
    },
    "fundus_api.get_project_encounter_set_queues": _screen(Action.TASKS_VIEW),
    **{
        endpoint: _exact(
            Action.PROJECT_GRADER_ALLOCATIONS_VIEW, "project_allocation_plan"
        )
        for endpoint in (
            "fundus_api.get_project_grader_allocation_candidates",
            "fundus_api.get_project_grader_allocations",
        )
    },
    **{
        endpoint: _exact(
            Action.PROJECT_GRADER_ALLOCATIONS_MANAGE,
            "project_allocation_target",
        )
        for endpoint in (
            "fundus_api.create_project_grader_allocation",
            "fundus_api.update_project_grader_allocation",
            "fundus_api.deactivate_project_grader_allocation",
        )
    },
    "fundus_api.update_project_grader_allocation_policy": _exact(
        Action.PROJECT_GRADER_ALLOCATIONS_ENFORCEMENT_MANAGE, "project"
    ),
    "fundus_api.get_lab_units": _exact(Action.ACCOUNT_PROFILE_VIEW, "user"),
    "fundus_api.get_hospital": _exact(
        Action.UPLOAD_LAB_UNIT_VIEW, "upload_lab_unit"
    ),
    **{
        endpoint: _exact(Action.JOBS_RESULT_VIEW, "job")
        for endpoint in (
            "fundus_api.get_upload_status",
            "fundus_api.direct_upload_status",
        )
    },
    **{
        endpoint: _screen(Action.UPLOAD_WORKSPACE_VIEW)
        for endpoint in (
            "fundus_api.direct_upload_form",
            "fundus_api.direct_upload_workspace",
        )
    },
    "fundus_api.create_direct_upload_web": _exact(
        Action.UPLOAD_CREATE, "upload_target"
    ),
    # Browser authentication. CAPTCHA generation and validation, reset workflow
    # rules, and password policy remain application concerns. Authz classifies
    # only public entry, exact signed reset credentials, and the current user.
    **{
        endpoint: EndpointPolicy(EndpointMode.PUBLIC, Action.AUTH_LOGIN)
        for endpoint in (
            "auth.login",
            "auth.refresh_captcha",
            "auth.captcha_audio",
            "auth.check_session",
        )
    },
    "auth.forgot_password": EndpointPolicy(
        EndpointMode.PUBLIC, Action.AUTH_PASSWORD_RESET_REQUEST
    ),
    "auth.reset_password": _signed(
        Action.AUTH_PASSWORD_RESET_COMPLETE, "password_reset_credential"
    ),
    **{
        endpoint: _signed(
            Action.AUTH_PASSWORD_RESET_STATUS, "password_reset_credential"
        )
        for endpoint in ("auth.email_sse", "auth.check_email_status")
    },
    "auth.logout": _exact(Action.AUTH_LOGOUT, "user"),
    "auth.ping": _exact(Action.AUTH_SESSION_KEEPALIVE, "user"),
    "auth.confirm_password": _exact(Action.AUTH_REAUTH, "user"),
    **{
        endpoint: _exact(Action.PROJECT_REMOTE_INFERENCE_CONFIG_VIEW, "project")
        for endpoint in (
            "fundus_api.get_project_manual_remote_inference_workflows",
            "fundus_api.get_project_automated_remote_inference_workflows",
            "fundus_api.get_project_dr_dme_encounter_workflow",
        )
    },
    **{
        endpoint: _exact(Action.PROJECT_REMOTE_INFERENCE_CONFIG_MANAGE, "project")
        for endpoint in (
            "fundus_api.save_project_manual_remote_inference_workflows",
            "fundus_api.save_project_automated_remote_inference_workflows",
            "fundus_api.save_project_dr_dme_encounter_workflow",
        )
    },
    "fundus_api.get_recent_project_wadhwani_encounter_set_jobs": _exact(
        Action.PROJECT_WAI_RESULTS, "project"
    ),
    "fundus_api.resume_interrupted_wadhwani_encounter_set_job": _exact(
        Action.PROJECT_REMOTE_INFERENCE_JOB_RESUME, "job"
    ),
    "fundus_api.get_encounter_remote_inference_candidates": _exact(
        Action.PROJECT_WAI_RUN, "project"
    ),
    "fundus_api.create_encounter_remote_inference_job": _exact(
        Action.PROJECT_REMOTE_INFERENCE_BATCH_RUN, "remote_inference_batch"
    ),
    "fundus_api.list_grading_schemes": _screen(
        Action.ADMIN_GRADING_ELIGIBILITY_MANAGE
    ),
    "fundus_api.create_grading_scheme": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    "fundus_api.get_grading_scheme": _exact(
        Action.ADMIN_GRADING_CONFIG_VIEW, "grading_config_record"
    ),
    **{
        endpoint: _exact(
            Action.ADMIN_GRADING_CONFIG_MANAGE, "grading_config_record"
        )
        for endpoint in (
            "fundus_api.update_grading_scheme",
            "fundus_api.duplicate_grading_scheme",
            "fundus_api.delete_grading_scheme",
            "fundus_api.create_grading_scheme_grade",
            "fundus_api.update_grading_scheme_grade",
            "fundus_api.activate_grading_scheme_grade",
            "fundus_api.deactivate_grading_scheme_grade",
        )
    },
    "fundus_api.list_encounter_set_types": _screen(
        Action.ADMIN_GRADING_ELIGIBILITY_MANAGE
    ),
    "fundus_api.create_encounter_set_type": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    **{
        endpoint: _exact(Action.ADMIN_GRADING_CONFIG_VIEW, "grading_config_record")
        for endpoint in (
            "fundus_api.get_encounter_set_type",
            "fundus_api.export_encounter_set_type_schema",
        )
    },
    **{
        endpoint: _exact(
            Action.ADMIN_GRADING_CONFIG_MANAGE, "grading_config_record"
        )
        for endpoint in (
            "fundus_api.update_encounter_set_type",
            "fundus_api.activate_encounter_set_type",
            "fundus_api.deactivate_encounter_set_type",
            "fundus_api.delete_encounter_set_type",
            "fundus_api.delete_encounter_set_type_rest",
        )
    },
    "fundus_api.get_active_workbench_sessions": _screen(
        Action.GRADING_WORKBENCH_SESSIONS_LIST
    ),
    "fundus_api.get_my_workbench_submissions": _screen(
        Action.GRADING_WORKBENCH_SUBMISSIONS_LIST
    ),
    "fundus_api.get_workbench_session": _exact(
        Action.GRADING_WORKBENCH_SESSION_VIEW, "workbench_session"
    ),
    "fundus_api.resume_workbench_session": _exact(
        Action.GRADING_WORKBENCH_SESSION_RESUME, "workbench_session"
    ),
    "fundus_api.heartbeat_workbench_session": _exact(
        Action.GRADING_WORKBENCH_SESSION_HEARTBEAT, "workbench_session"
    ),
    "fundus_api.release_workbench_session": _exact(
        Action.GRADING_WORKBENCH_SESSION_RELEASE, "workbench_session"
    ),
    "fundus_api.save_workbench_session_draft": _exact(
        Action.GRADING_WORKBENCH_SESSION_DRAFT, "workbench_session"
    ),
    "fundus_api.submit_workbench_session": _exact(
        Action.GRADING_WORKBENCH_SESSION_SUBMIT, "workbench_session"
    ),
    **{
        endpoint: _exact(
            Action.GRADING_WORKBENCH_ACQUIRE, "workbench_acquisition_target"
        )
        for endpoint in (
            "fundus_api.acquire_workbench_session",
            "fundus_api.acquire_linked_followup_workbench_session",
            "fundus_api.acquire_task_workbench_session",
            "fundus_api.acquire_package_workbench_session",
        )
    },
    "fundus_api.acquire_revision_workbench_session": _exact(
        Action.GRADING_WORKBENCH_REVISION_ACQUIRE,
        "workbench_acquisition_target",
    ),
    **{
        endpoint: _screen(Action.ADMIN_SECURITY_VIEW)
        for endpoint in (
            "fundus_api.list_remidio_connections",
            "fundus_api.list_remidio_routing_rules",
            "fundus_api.list_remidio_api_source_rules",
            "fundus_api.list_remidio_api_bindings",
            "fundus_api.list_remidio_api_routing_profiles",
            "fundus_api.list_remidio_api_routing_rules",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation")
        for endpoint in (
            "fundus_api.create_remidio_connection",
            "fundus_api.upsert_remidio_routing_rule",
            "fundus_api.upsert_remidio_api_source_rule",
            "fundus_api.upsert_remidio_api_binding",
            "fundus_api.upsert_remidio_api_routing_profile",
            "fundus_api.create_remidio_api_routing_profile_with_route",
            "fundus_api.upsert_remidio_api_routing_rule",
        )
    },
    **{
        endpoint: _exact(
            Action.ADMIN_REMIDIO_API_CONFIG_MANAGE, "remidio_config_record"
        )
        for endpoint in (
            "fundus_api.patch_remidio_connection",
            "fundus_api.refresh_remidio_token",
            "fundus_api.sync_remidio_sites",
            "fundus_api.patch_remidio_site",
            "fundus_api.delete_remidio_api_routing_profile",
            "fundus_api.set_remidio_api_routing_rule_status",
            "fundus_api.delete_remidio_api_routing_rule",
            "fundus_api.sync_remidio_api_routing_profile",
            "fundus_api.pull_remidio_exams_by_date",
            "fundus_api.pull_remidio_latest_patient_exam",
            "fundus_api.ingest_remidio_staged_files",
        )
    },
    "fundus_api.list_remidio_sites": _exact(
        Action.ADMIN_REMIDIO_API_CONFIG_VIEW, "remidio_config_record"
    ),
    "fundus_api.queue_encounter_set_attachment_ocr": {
        "GET": _exact(Action.REMIDIO_ATTACHMENT_OCR_VIEW, "remidio_attachment"),
        "POST": _exact(
            Action.REMIDIO_ATTACHMENT_OCR_PROCESS, "remidio_attachment"
        ),
    },
    "fundus_api.queue_project_pending_encounter_set_attachment_ocr": {
        "GET": _exact(Action.PROJECT_REMIDIO_ATTACHMENT_OCR_VIEW, "project"),
        "POST": _exact(Action.PROJECT_REMIDIO_ATTACHMENT_OCR_PROCESS, "project"),
    },
    **{
        endpoint: _exact(
            Action.PROJECT_REMIDIO_SYNC, "remidio_project_sync_target"
        )
        for endpoint in (
            "fundus_api.sync_remidio_api_project",
            "fundus_api.sync_selected_remidio_api_project",
        )
    },
    **{
        endpoint: _exact(Action.PROJECT_REMIDIO_SYNC_JOB_MANAGE, "job")
        for endpoint in (
            "fundus_api.pause_remidio_api_project_sync_job",
            "fundus_api.resume_remidio_api_project_sync_job",
            "fundus_api.cancel_remidio_api_project_sync_job",
        )
    },
    "admin.sensitive_operations_audit": _screen(Action.ADMIN_SENSITIVE_AUDIT_VIEW),
    "admin.sensitive_operation_details": _exact(
        Action.ADMIN_SENSITIVE_AUDIT_DETAIL_VIEW, "sensitive_audit_event"
    ),
    "admin.s3_sync_dashboard": _screen(Action.ADMIN_S3_SYNC_VIEW),
    "admin.s3_sync_hospital_detail": _exact(
        Action.ADMIN_S3_SYNC_QUERY, "s3_sync_query"
    ),
    "admin.s3_sync_status_api": _exact(
        Action.ADMIN_S3_SYNC_QUERY, "s3_sync_query"
    ),
    "admin.s3_sync_stats_api": _screen(Action.ADMIN_S3_SYNC_VIEW),
    "admin.s3_sync_retry": _exact(Action.ADMIN_S3_SYNC_RETRY, "s3_sync_record"),
    "admin.task_backfill_admin": _screen(Action.ADMIN_TASK_BACKFILL_VIEW),
    "admin.task_backfill_run": _exact(
        Action.ADMIN_TASK_BACKFILL_RUN, "task_backfill_target"
    ),
    **{
        endpoint: _screen(Action.ADMIN_SYSTEM_STATUS_VIEW)
        for endpoint in (
            "admin.admin_status",
            "admin.api_admin_status",
            "admin.api_sequences_status",
            "admin.api_celery_task_status",
        )
    },
    **{
        endpoint: _screen(Action.ADMIN_DASHBOARD_VIEW)
        for endpoint in (
            "admin.cve_security_report",
            "admin.api_cve_summary",
            "admin.htmx_cve_packages",
            "admin.htmx_cve_vulnerabilities",
            "admin.htmx_cve_scan_history",
            "admin.package_updates_report",
            "admin.api_package_updates_summary",
            "admin.htmx_package_list",
            "admin.htmx_scan_history",
            "admin.api_package_updates_yaml",
            "admin.api_package_updates_instructions",
        )
    },
    **{
        endpoint: _screen(Action.ADMIN_SECURITY_VIEW)
        for endpoint in (
            "admin.cve_report_text",
            "admin.api_cve_scan_history",
            "admin.api_package_updates_scan_history",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation")
        for endpoint in (
            "admin.api_cve_refresh",
            "admin.api_package_updates_refresh",
            "admin.refresh_sequences",
        )
    },
    **{
        endpoint: _screen(Action.ADMIN_SYSTEM_STATUS_VIEW)
        for endpoint in (
            "admin.thumbnail_management",
            "admin.api_thumbnail_stats",
            "admin.api_maintenance_status",
            "admin.api_thumbnail_health_check",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_STORAGE_OPERATION, "system_operation")
        for endpoint in (
            "admin.api_manual_maintenance",
            "admin.api_cleanup_orphaned",
            "admin.api_regenerate_missing",
            "admin.api_validate_integrity",
            "admin.api_full_maintenance",
        )
    },
    **{
        endpoint: _screen(Action.ADMIN_DASHBOARD_VIEW)
        for endpoint in (
            "admin.image_metadata_admin",
            "admin.image_metadata_status",
            "admin.metadata_backfill_admin",
            "admin.metadata_backfill_admin_alias",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_METADATA_OPERATION, "system_operation")
        for endpoint in (
            "admin.image_metadata_backfill",
            "admin.metadata_backfill_run",
            "admin.image_metadata_run_pii_queue",
            "admin.image_metadata_stop_all",
            "admin.image_metadata_clear_queued",
            "admin.image_metadata_clear_running",
        )
    },
    **{
        endpoint: _screen(Action.ADMIN_SECURITY_VIEW)
        for endpoint in (
            "admin.materialized_view_status",
            "admin.api_materialized_view_status",
            "admin.api_last_refresh",
            "admin.api_schedule_status",
        )
    },
    "admin.manual_refresh": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    "admin.email_settings_list": _screen(Action.ADMIN_SECURITY_VIEW),
    "admin.create_email_settings": {
        "GET": _screen(Action.ADMIN_SECURITY_VIEW),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "admin.edit_email_settings": {
        "GET": _exact(Action.ADMIN_EMAIL_SETTINGS_VIEW, "email_settings_config"),
        "POST": _exact(Action.ADMIN_EMAIL_SETTINGS_MANAGE, "email_settings_config"),
    },
    **{
        endpoint: _exact(
            Action.ADMIN_EMAIL_SETTINGS_MANAGE, "email_settings_config"
        )
        for endpoint in (
            "admin.test_email_settings",
            "admin.delete_email_settings",
            "admin.activate_email_settings",
            "admin.api_test_current_email_config",
            "admin.send_sample_email",
        )
    },
    "admin.task_review_inconsistency": _screen(Action.ADMIN_SYSTEM_STATUS_VIEW),
    "admin.apply_review_as_final": _exact(
        Action.ADMIN_GRADING_REPAIR_APPLY_REVIEW, "grading_repair_target"
    ),
    "admin.grading_state_inconsistencies": {
        "GET": _screen(Action.ADMIN_SECURITY_VIEW),
        "POST": _exact(
            Action.ADMIN_GRADING_REPAIR_RESET_BATCH, "grading_repair_batch"
        ),
    },
    "admin.linked_task_inconsistencies": _screen(Action.ADMIN_SECURITY_VIEW),
    **{
        endpoint: _screen(Action.ADMIN_SECURITY_VIEW)
        for endpoint in (
            "rate_limit_admin.index",
            "rate_limit_admin.status",
            "rate_limit_admin.get_my_key",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation")
        for endpoint in (
            "rate_limit_admin.clear_limit",
            "rate_limit_admin.clear_limit_ajax",
            "rate_limit_admin.clear_all",
        )
    },
    "admin.upload_profiles_admin": _screen(Action.ADMIN_UPLOAD_PROFILES_MANAGE),
    "admin.upload_project_create_workspace": _screen(
        Action.ADMIN_UPLOAD_PROFILES_MANAGE
    ),
    "admin.upload_projects_admin": _screen(Action.AUTHORIZATION_GRANTS_VIEW),
    "admin.upload_project_workspace": _exact(Action.PROJECT_VIEW, "project"),
    "admin.upload_metadata_fields_admin": _screen(Action.ADMIN_LOOKUP_MANAGE),
    "admin.upload_metadata_fields_list": _screen(Action.ADMIN_LOOKUP_MANAGE),
    "admin.s3_configs_list": _screen(Action.ADMIN_S3_MANAGE),
    "admin.s3_configs_api_list": _screen(Action.ADMIN_S3_MANAGE),
    "admin.s3_config_create": {
        "GET": _screen(Action.ADMIN_S3_MANAGE),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "admin.s3_config_edit": {
        "GET": _exact(Action.ADMIN_S3_CONFIG_VIEW, "s3_config"),
        "POST": _exact(Action.ADMIN_S3_CONFIG_MANAGE, "s3_config"),
    },
    **{
        endpoint: _exact(Action.ADMIN_S3_CONFIG_MANAGE, "s3_config")
        for endpoint in (
            "admin.s3_config_delete",
            "admin.s3_config_activate",
            "admin.s3_config_test_connection",
            "admin.s3_config_rotate_pepper",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation")
        for endpoint in (
            "admin.s3_config_api_test_connection_modal",
            "admin.s3_config_api_create",
        )
    },
    "admin.admin_settings": {
        "GET": _screen(Action.ADMIN_SYSTEM_MANAGE),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "admin.upload_settings": {
        "GET": _screen(Action.ADMIN_SYSTEM_MANAGE),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "admin.database_dump": {
        "GET": _screen(Action.ADMIN_SECURITY_VIEW),
        "POST": _exact(Action.ADMIN_DATABASE_EXPORT, "system_operation"),
    },
    "admin.database_excel_export": {
        "GET": _screen(Action.ADMIN_SECURITY_VIEW),
        "POST": _exact(Action.ADMIN_DATABASE_EXPORT, "system_operation"),
    },
    "admin.get_database_info": _screen(Action.ADMIN_SECURITY_VIEW),
    "admin.get_database_tables": _screen(Action.ADMIN_SECURITY_VIEW),
    "admin.database_restore.index": _screen(Action.ADMIN_SECURITY_VIEW),
    **{
        endpoint: _exact(Action.ADMIN_DATABASE_RESTORE, "system_operation")
        for endpoint in (
            "admin.database_restore.upload_file",
            "admin.database_restore.restore_database",
            "admin.database_restore.cancel_restore",
        )
    },
    "admin.disk_usage": _screen(Action.ADMIN_SECURITY_VIEW),
    "admin.delete_duplicates": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    "admin.delete_old_processed_zips": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    "admin.log_viewer": _screen(Action.ADMIN_SECURITY_VIEW),
    "admin.malicious_uploads": _screen(Action.ADMIN_SECURITY_VIEW),
    "admin.list_upload_quotas": _screen(Action.ADMIN_SYSTEM_STATUS_VIEW),
    "admin.upload_quota_redirect": _screen(Action.ADMIN_SYSTEM_STATUS_VIEW),
    "admin.update_upload_quota": _exact(Action.ADMIN_UPLOAD_QUOTA_MANAGE, "user"),
    **{
        endpoint: {
            "GET": _screen(Action.ADMIN_LOOKUP_MANAGE),
            "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
        }
        for endpoint in (
            "admin.list_hospitals",
            "admin.list_lab_units",
            "admin.list_diseases",
            "admin.list_cameras",
            "admin.list_areas",
        )
    },
    **{
        endpoint: {
            "GET": _exact(Action.ADMIN_LOOKUP_RECORD_VIEW, "lookup_record"),
            "POST": _exact(Action.ADMIN_LOOKUP_RECORD_MANAGE, "lookup_record"),
        }
        for endpoint in (
            "admin.edit_hospital",
            "admin.edit_lab_unit",
            "admin.edit_disease",
            "admin.edit_camera",
            "admin.edit_area",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_LOOKUP_RECORD_MANAGE, "lookup_record")
        for endpoint in (
            "admin.delete_hospital",
            "admin.delete_lab_unit",
            "admin.delete_disease",
            "admin.delete_camera",
            "admin.delete_area",
        )
    },
    "admin.list_disease_gradings": {
        "GET": _screen(Action.ADMIN_GRADING_ELIGIBILITY_MANAGE),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "admin.get_grading_features": _exact(
        Action.ADMIN_GRADING_CONFIG_VIEW, "grading_config_record"
    ),
    "admin.delete_disease_grading": _exact(
        Action.ADMIN_GRADING_CONFIG_MANAGE, "grading_config_record"
    ),
    "admin.linked_disease_gradings_list": {
        "GET": _screen(Action.ADMIN_GRADING_ELIGIBILITY_MANAGE),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "admin.get_linked_disease_hierarchy": _screen(
        Action.ADMIN_GRADING_ELIGIBILITY_MANAGE
    ),
    "admin.update_linked_disease_hierarchy": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    "admin.edit_linked_disease_grading": {
        "GET": _exact(Action.ADMIN_GRADING_CONFIG_VIEW, "grading_config_record"),
        "POST": _exact(Action.ADMIN_GRADING_CONFIG_MANAGE, "grading_config_record"),
    },
    "admin.delete_linked_disease_grading": _exact(
        Action.ADMIN_GRADING_CONFIG_MANAGE, "grading_config_record"
    ),
    **{
        endpoint: _screen(Action.ADMIN_GRADING_ELIGIBILITY_MANAGE)
        for endpoint in (
            "admin.grading_schemes_admin",
            "admin.grading_schemes_list",
            "admin.grading_scheme_new",
            "admin.encounter_set_types_admin",
            "admin.encounter_set_types_list",
            "admin.encounter_set_type_new",
        )
    },
    **{
        endpoint: _exact(Action.ADMIN_GRADING_CONFIG_VIEW, "grading_config_record")
        for endpoint in (
            "admin.grading_scheme_detail",
            "admin.grading_scheme_edit",
            "admin.encounter_set_type_edit",
            "admin.encounter_set_type_view",
        )
    },
    "admin.manage_eligibility_users": _screen(Action.ADMIN_DASHBOARD_VIEW),
    "admin.edit_eligibility": {
        "GET": _exact(Action.ADMIN_GRADING_ELIGIBILITY_USER_MANAGE, "user"),
        "POST": _exact(Action.ADMIN_GRADING_ELIGIBILITY_USER_MANAGE, "user"),
    },
    **{
        endpoint: _screen(Action.ADMIN_SECURITY_VIEW)
        for endpoint in (
            "admin.remidio_admin",
            "admin.remidio_workspace",
            "admin.remidio_api_routing_dashboard",
            "admin.remidio_api_routing_workspace",
            "admin.stuck_remidio_uploads_status",
            "admin.remidio_encounter_migration",
            "admin.iitk_admin",
            "admin.iitk_workspace",
        )
    },
    "admin.cleanup_stuck_remidio_uploads": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    "fundus_api.remidio_migration_projects": _screen(Action.ADMIN_SECURITY_VIEW),
    **{
        endpoint: _exact(Action.ADMIN_REMIDIO_ENCOUNTER_MIGRATION_VIEW, "project")
        for endpoint in (
            "fundus_api.remidio_migration_source_dates",
            "fundus_api.remidio_migration_encounters",
        )
    },
    "fundus_api.remidio_migration_preview": _exact(
        Action.ADMIN_REMIDIO_ENCOUNTER_MIGRATION_PREVIEW,
        "remidio_encounter_migration_target",
    ),
    "fundus_api.remidio_migration_apply": _exact(
        Action.ADMIN_REMIDIO_ENCOUNTER_MIGRATION_APPLY,
        "remidio_encounter_migration_target",
    ),
    **{
        endpoint: _screen(Action.ADMIN_IITK_VIEW)
        for endpoint in (
            "fundus_api.list_iitk_configurations",
            "fundus_api.list_iitk_site_mappings",
        )
    },
    "fundus_api.get_iitk_project_configuration": _exact(
        Action.ADMIN_IITK_PROJECT_CONFIGURATION_VIEW, "project"
    ),
    "fundus_api.save_iitk_project_configuration": _exact(
        Action.ADMIN_IITK_PROJECT_CONFIGURATION_MANAGE, "project"
    ),
    "fundus_api.save_iitk_configuration": _exact(
        Action.ADMIN_IITK_CONFIGURATION_CREATE, "iitk_configuration_target"
    ),
    "fundus_api.patch_iitk_configuration": _exact(
        Action.ADMIN_IITK_CONFIGURATION_MANAGE, "iitk_configuration"
    ),
    "fundus_api.browse_iitk_sessions": _exact(
        Action.ADMIN_IITK_CONFIGURATION_VIEW, "iitk_configuration"
    ),
    "fundus_api.queue_iitk_sync": _exact(
        Action.ADMIN_IITK_CONFIGURATION_SYNC, "iitk_configuration"
    ),
    "admin.list_and_create_ai_model": {
        "GET": _screen(Action.ADMIN_SYSTEM_MANAGE),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "admin.edit_ai_model": {
        "GET": _exact(Action.ADMIN_EXECUTABLE_CONFIG_VIEW, "executable_config_record"),
        "POST": _exact(
            Action.ADMIN_EXECUTABLE_CONFIG_MANAGE, "executable_config_record"
        ),
    },
    **{
        endpoint: _exact(
            Action.ADMIN_EXECUTABLE_CONFIG_MANAGE, "executable_config_record"
        )
        for endpoint in ("admin.delete_ai_model", "admin.test_ai_model_health")
    },
    "admin.celery_schedule_list": _screen(Action.ADMIN_SYSTEM_MANAGE),
    "admin.celery_schedule_create": _exact(
        Action.ADMIN_SYSTEM_OPERATION, "system_operation"
    ),
    **{
        endpoint: _exact(
            Action.ADMIN_EXECUTABLE_CONFIG_MANAGE, "executable_config_record"
        )
        for endpoint in (
            "admin.celery_schedule_update",
            "admin.celery_schedule_delete",
        )
    },
    **{
        endpoint: _screen(Action.ADMIN_SECURITY_VIEW)
        for endpoint in (
            "admin.manage_roles",
            "admin.role_usage",
            "admin.routes_by_role",
        )
    },
    **{
        endpoint: _screen(Action.ADMIN_USERS_WORKSPACE_VIEW)
        for endpoint in (
            "admin.users_list",
            "admin.user_created",
            "fundus_api.api_admin_users_activity",
        )
    },
    "admin.user_detail": _exact(Action.ADMIN_USERS_VIEW, "user"),
    "admin.add_user": {
        "GET": _screen(Action.ADMIN_USERS_WORKSPACE_VIEW),
        "POST": _exact(Action.ADMIN_USERS_CREATE, "user_creation_target"),
    },
    "admin.change_password": {
        "GET": _screen(Action.ADMIN_SECURITY_VIEW),
        # The request adapter resolves the submitted username to the stored user.
        "POST": _exact(Action.ADMIN_USERS_MANAGE, "user"),
    },
    "admin.edit_user": {
        "GET": _exact(Action.ADMIN_USERS_VIEW, "user"),
        "POST": _exact(Action.ADMIN_USERS_MANAGE, "user"),
    },
    "admin.users_update": _exact(Action.ADMIN_USERS_MANAGE, "user"),
    "admin.revoke_mobile_session": _exact(
        Action.API_MOBILE_SESSION_MANAGE, "mobile_session"
    ),
    "admin.issue_device_enrolment_code": _exact(Action.ADMIN_USERS_MANAGE, "user"),
    "admin.update_mobile_device_status": _exact(Action.ADMIN_USERS_MANAGE, "user"),
    "fundus_api.project_role_grants": {
        "GET": _exact(Action.PROJECT_GRANTS_VIEW, "project"),
        "POST": _exact(Action.AUTHORIZATION_GRANTS_MANAGE, "grant_target"),
        "PUT": _exact(Action.AUTHORIZATION_GRANTS_MANAGE, "grant_target"),
    },
    "fundus_api.remove_project_role_grant": {
        "DELETE": _exact(Action.AUTHORIZATION_GRANTS_MANAGE, "grant_target"),
        "POST": _exact(Action.AUTHORIZATION_GRANTS_MANAGE, "grant_target"),
    },
    # Upload-profile governance. Body-only project references must be resolved
    # to the stored project before any assignment or relationship mutation.
    "fundus_api.create_upload_profile_project": _screen(
        Action.ADMIN_UPLOAD_PROFILES_MANAGE
    ),
    "fundus_api.update_upload_profile_project": _exact(
        Action.PROJECT_ACCESS_MANAGE, "project"
    ),
    "fundus_api.project_referral_diseases": {
        "GET": _exact(Action.PROJECT_VIEW, "project"),
        "POST": _exact(Action.PROJECT_ACCESS_MANAGE, "project"),
        "PUT": _exact(Action.PROJECT_ACCESS_MANAGE, "project"),
    },
    "fundus_api.project_encounter_set_permissions": {
        "GET": _exact(Action.PROJECT_VIEW, "project"),
        "POST": _exact(Action.PROJECT_ACCESS_MANAGE, "project"),
        "PUT": _exact(Action.PROJECT_ACCESS_MANAGE, "project"),
    },
    "fundus_api.add_upload_profile_investigator": _exact(
        Action.PROJECT_ACCESS_MANAGE, "project"
    ),
    "fundus_api.assign_upload_profile_user": _exact(
        Action.PROJECT_UPLOADERS_MANAGE, "project"
    ),
    "fundus_api.remove_upload_profile_user": _exact(
        Action.PROJECT_UPLOADERS_MANAGE, "project"
    ),
    "fundus_api.enable_upload_profile_for_project": _exact(
        Action.PROJECT_UPLOADERS_MANAGE, "project"
    ),
    "fundus_api.activate_project_upload_profile": _exact(
        Action.PROJECT_UPLOADERS_MANAGE, "project"
    ),
    "fundus_api.deactivate_project_upload_profile": _exact(
        Action.PROJECT_UPLOADERS_MANAGE, "project"
    ),
    "fundus_api.create_upload_profile": _screen(
        Action.ADMIN_UPLOAD_PROFILES_MANAGE
    ),
    **{
        endpoint: _exact(Action.ADMIN_UPLOAD_PROFILES_UPDATE, "upload_profile")
        for endpoint in (
            "fundus_api.update_upload_profile",
            "fundus_api.activate_upload_profile",
            "fundus_api.deactivate_upload_profile",
            "fundus_api.duplicate_upload_profile",
        )
    },
    # Direct-upload workspaces use method-specific contracts so a GET page
    # decision can never authorize POST mutations handled by the same view.
    "direct_uploads.upload_index": _screen(Action.UPLOAD_WORKSPACE_VIEW),
    "direct_uploads.upload": _screen(Action.UPLOAD_WORKSPACE_VIEW),
    "direct_uploads.dashboard": {
        "GET": _screen(Action.UPLOAD_WORKSPACE_VIEW),
        "POST": _exact(Action.UPLOAD_DIRECT_BATCH_UPDATE, "direct_upload_batch"),
    },
    "direct_uploads.edit_upload": {
        "GET": _exact(Action.VERIFICATION_DIRECT_VIEW, "direct_image_upload"),
        "POST": _exact(Action.UPLOAD_DIRECT_UPDATE, "direct_image_upload"),
    },
    "direct_uploads.edit_image": _exact(
        Action.VERIFICATION_DIRECT_VIEW, "direct_image_upload"
    ),
    "direct_uploads.restore_original": _exact(
        Action.UPLOAD_DIRECT_UPDATE, "direct_image_upload"
    ),
    "direct_uploads.save_edited_image": _exact(
        Action.UPLOAD_DIRECT_UPDATE, "direct_image_upload"
    ),
    "direct_uploads.api_upload_status": _exact(Action.JOBS_RESULT_VIEW, "job"),
    "direct_uploads.pregraded_upload": {
        "GET": _screen(Action.UPLOAD_PREGRADED_WORKSPACE_VIEW),
        "POST": _exact(Action.UPLOAD_PREGRADED_CREATE, "upload_target"),
    },
    "direct_uploads.pregraded_grades": {
        "GET": _screen(Action.UPLOAD_PREGRADED_WORKSPACE_VIEW),
        "POST": _exact(Action.UPLOAD_PREGRADED_CREATE, "upload_target"),
    },
    "direct_uploads.recent_pregraded_grades": _screen(
        Action.UPLOAD_PREGRADED_WORKSPACE_VIEW
    ),
    "direct_uploads.get_lab_units": _exact(
        Action.AUTHORIZATION_ME_UPLOAD_OPTIONS_VIEW, "user"
    ),
    "direct_uploads.get_hospital": _exact(
        Action.AUTHORIZATION_ME_UPLOAD_OPTIONS_VIEW, "user"
    ),
    # Remidio project workspaces. Collection pages are admission only; file,
    # archive, mutation and job routes bind exact stored resources.
    **{
        endpoint: _screen(Action.PROJECT_ENCOUNTERSETS_WORKSPACE_VIEW_PII)
        for endpoint in (
            "remidio_api_uploads.encounter_set_browser",
            "remidio_api_uploads.encounter_set_browser_workspace",
        )
    },
    **{
        endpoint: _screen(Action.PROJECT_ENCOUNTERSETS_WORKSPACE_VIEW)
        for endpoint in (
            "remidio_api_uploads.encounter_set_browser_no_pii",
            "remidio_api_uploads.encounter_set_browser_no_pii_workspace",
        )
    },
    "remidio_api_uploads.encounter_set_browser_no_pii_download": _exact(
        Action.PROJECT_ENCOUNTERSETS_BROWSE, "encounter_set"
    ),
    "remidio_api_uploads.encounter_set_attachment": _exact(
        Action.PROJECT_ENCOUNTERSETS_BROWSE_PII, "encounter_set"
    ),
    **{
        endpoint: _screen(Action.INFERENCE_WAI_SUMMARY)
        for endpoint in (
            "remidio_api_uploads.encounter_set_wadhwani_inference",
            "remidio_api_uploads.encounter_set_wadhwani_inference_workspace",
        )
    },
    "remidio_api_uploads.encounter_set_wadhwani_inference_run": _wai_project(
        "wai_workflow_project"
    ),
    "remidio_api_uploads.encounter_set_wadhwani_inference_job": _exact(
        Action.JOBS_RESULT_VIEW, "job"
    ),
    "remidio_api_uploads.encounter_set_wadhwani_inference_job_status": _exact(
        Action.JOBS_RESULT_VIEW, "job"
    ),
    "remidio_api_uploads.remidio_api_sync": _screen(
        Action.PROJECT_UPLOAD_WORKSPACE_VIEW
    ),
    "remidio_api_uploads.remidio_api_sync_workspace": _screen(
        Action.PROJECT_UPLOAD_WORKSPACE_VIEW
    ),
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
    **{
        endpoint: _screen(Action.PREPROCESS_DASHBOARD_VIEW)
        for endpoint in (
            "verify_remedio_dr.verify_dr_list",
            "verify_remedio_glaucoma.glaucoma_results",
            "verify_remedio_glaucoma.glaucoma_list",
            "verify_remedio_nodr.nodr_list",
        )
    },
    "verify_remedio_glaucoma.glaucoma_clean_workflow": {
        "GET": _screen(Action.PREPROCESS_DASHBOARD_VIEW),
        "POST": _exact(Action.ADMIN_SYSTEM_OPERATION, "system_operation"),
    },
    "tasks.create_intra_rater_batch": _exact(
        Action.INTRA_RATER_BATCH_CREATE, "intra_rater_batch_target"
    ),
    **{
        endpoint: _screen(action)
        for endpoint, action in (
            ("tasks.list_intra_rater_batches", Action.INTRA_RATER_BATCH_VIEW),
            ("tasks.list_my_intra_rater_tasks", Action.INTRA_RATER_TASKS_LIST),
            ("tasks.get_intra_rater_kpi_data", Action.INTRA_RATER_KPI_VIEW),
            ("tasks.intra_rater_dashboard", Action.INTRA_RATER_TASKS_LIST),
            ("tasks.intra_rater_admin", Action.INTRA_RATER_BATCH_VIEW),
        )
    },
    "tasks.intra_rater_viewer": _exact(Action.TASKS_VIEWER_VIEW, "image"),
    "tasks.submit_intra_rater_grade": _exact(
        Action.INTRA_RATER_TASK_SUBMIT, "intra_rater_task"
    ),
    **{
        endpoint: _screen(Action.ANALYTICS_KPI_VIEW)
        for endpoint in (
            "fundus_api.get_filtered_dataframe",
            "fundus_api.get_filtered_dataframe_excel",
            "fundus_api.year_month_wise_uploads",
            "fundus_api.dr_reports_count",
            "fundus_api.glaucoma_reports_count",
            "fundus_api.images_count",
            "fundus_api.dr_results_distribution",
            "fundus_api.glaucoma_results_distribution",
            "fundus_api.vcdr_distribution",
            "fundus_api.get_filtered_direct_dataframe",
            "fundus_api.get_filtered_direct_dataframe_excel",
            "fundus_api.get_upload_metrics",
        )
    },
    **{
        endpoint: _screen(Action.ANALYTICS_HOSPITAL_DASHBOARD_VIEW)
        for endpoint in (
            "analytics.hospital_dashboard_page",
            "analytics.hospital_dashboard_disease_view",
            "analytics.hospital_dashboard_lab_disease_view",
            "analytics.hospital_dashboard_user_view",
            "analytics.hospital_dashboard_roster_view",
            "analytics.hospital_dashboard_encounter_view",
        )
    },
    **{
        endpoint: _screen(Action.INFERENCE_WAI_SUMMARY)
        for endpoint in (
            "fundus_api.wai_api_statistics_options",
            "fundus_api.wai_api_statistics_summary",
            "fundus_api.wai_api_statistics_images",
            "fundus_api.wai_api_statistics_encounters",
        )
    },
    "fundus_api.wai_api_statistics_retry": _exact(
        Action.INFERENCE_WAI_RUN_RETRY, "inference_result"
    ),
    "fundus_api.get_project_lab_units": _exact(Action.PROJECT_VIEW, "project"),
    "fundus_api.put_project_lab_units": _exact(
        Action.PROJECT_ACCESS_MANAGE, "project"
    ),
    "jobs.list_recent_jobs": _screen(Action.JOBS_VIEW),
    **{
        endpoint: _exact(Action.JOBS_RESULT_VIEW, "job")
        for endpoint in (
            "jobs.job_status_json",
            "jobs.job_status_page",
            "jobs.upload_results",
            "jobs.upload_processing",
        )
    },
    "jobs.regenerate_export": _exact(Action.JOBS_REGENERATE, "job"),
    **{
        endpoint: _screen(Action.ADMIN_UPLOAD_METADATA_FIELDS_VIEW)
        for endpoint in (
            "fundus_api.list_upload_metadata_field_definitions",
            "fundus_api.check_upload_metadata_field_key",
        )
    },
    "fundus_api.create_upload_metadata_field_definition": _exact(
        Action.ADMIN_UPLOAD_METADATA_FIELDS_CREATE, "system_operation"
    ),
    **{
        endpoint: _exact(
            Action.ADMIN_UPLOAD_METADATA_FIELDS_MANAGE,
            "upload_metadata_field_definition",
        )
        for endpoint in (
            "fundus_api.update_upload_metadata_field_definition",
            "fundus_api.activate_upload_metadata_field_definition",
            "fundus_api.deactivate_upload_metadata_field_definition",
        )
    },
    **{
        endpoint: _exact(Action.VERIFICATION_REMIDIO_VIEW, "encounter")
        for endpoint in (
            "verify_remedio_dr.verify_dr_detail",
            "verify_remedio_glaucoma.glaucoma_detail",
        )
    },
    **{
        endpoint: {
            "GET": _exact(Action.VERIFICATION_REMIDIO_VIEW, "encounter"),
            "POST": _exact(Action.VERIFICATION_REMIDIO_UPDATE, "encounter"),
        }
        for endpoint in (
            "verify_remedio_dr.verify_dr_edit",
            "verify_remedio_glaucoma.glaucoma_edit",
            "verify_remedio_nodr.nodr_edit",
        )
    },
    **{
        endpoint: _exact(Action.VERIFICATION_REMIDIO_UPDATE, "encounter")
        for endpoint in (
            "verify_remedio_dr.verify_dr_mark_eye",
            "verify_remedio_dr.verify_dr_unverify",
            "verify_remedio_dr.verify_dr_verify",
            "verify_remedio_glaucoma.glaucoma_mark_eye",
            "verify_remedio_glaucoma.glaucoma_unverify",
            "verify_remedio_glaucoma.glaucoma_verify",
            "verify_remedio_nodr.nodr_mark_eye",
            "verify_remedio_nodr.nodr_unverify",
            "verify_remedio_nodr.nodr_verify",
        )
    },
}


def catalogued_endpoint_policy(
    endpoint: str | None, method: str | None = None
) -> EndpointPolicy | None:
    if not endpoint:
        return None
    configured = ROUTE_POLICIES.get(endpoint)
    if isinstance(configured, dict):
        return configured.get(method.upper()) if method else None
    return configured


def catalogued_endpoint_policies(endpoint: str | None) -> dict[str, EndpointPolicy]:
    """Return method-specific policies, or a wildcard policy for all methods."""
    configured = ROUTE_POLICIES.get(endpoint) if endpoint else None
    if isinstance(configured, dict):
        return dict(configured)
    return {"*": configured} if configured else {}
