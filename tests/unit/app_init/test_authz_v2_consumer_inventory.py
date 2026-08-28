import json
import subprocess
import sys

from app import create_app
from authz_v2.core.actions import Action
from authz_v2.flask.contracts import EndpointMode
from authz_v2.flask.route_catalogue import ROUTE_POLICIES
from celery_app import celery_app
from celery_tasks.tasks import _import_all
from scripts.authz_v2_inventory import (
    build_live_consumer_inventory,
)


def test_live_http_and_celery_inventory_matches_reviewed_baseline():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.authz_v2_inventory"],
        check=True,
        capture_output=True,
        text=True,
    )
    inventory = json.loads(result.stdout)
    assert inventory["counts"] == {
        "authz_v2": 417,
        "legacy_action_literal": 44,
        "legacy_unmapped": 219,
        "automation_unmapped": 47,
        "query_candidate_unmapped": 979,
    }
    assert (
        inventory["identity_fingerprint"]
        == "3dc7aa9c953027f2b6de76a8255ba66fece74e95dbfaf36c20faeaf7d07b6d53"
    )


def test_browser_authentication_family_is_classified_by_security_boundary():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source == "auth/routes.py"
    ]
    assert len(family) == 11
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in ("auth.reset_password", "auth.email_sse", "auth.check_email_status"):
        assert ROUTE_POLICIES[endpoint].resolver == "password_reset_credential"
    for endpoint in ("auth.logout", "auth.ping", "auth.confirm_password"):
        assert ROUTE_POLICIES[endpoint].resolver == "user"


def test_remote_inference_family_has_exact_project_job_and_batch_contracts():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source == "api/remote_inference.py"
    ]
    assert len(family) == 10
    assert {row.classification for row in family} == {"authz_v2"}
    assert (
        ROUTE_POLICIES["fundus_api.create_encounter_remote_inference_job"].resolver
        == "remote_inference_batch"
    )
    assert (
        ROUTE_POLICIES[
            "fundus_api.resume_interrupted_wadhwani_encounter_set_job"
        ].resolver
        == "job"
    )


def test_grading_scheme_api_family_has_exact_configuration_contracts():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source == "api/grading_schemes.py"
    ]
    assert len(family) == 10
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "fundus_api.get_grading_scheme",
        "fundus_api.update_grading_scheme",
        "fundus_api.update_grading_scheme_grade",
    ):
        assert ROUTE_POLICIES[endpoint].resolver == "grading_config_record"


def test_encounter_set_type_api_family_has_exact_configuration_contracts():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source == "api/encounter_set_types.py"
    ]
    assert len(family) == 9
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "fundus_api.get_encounter_set_type",
        "fundus_api.export_encounter_set_type_schema",
        "fundus_api.update_encounter_set_type",
        "fundus_api.delete_encounter_set_type_rest",
    ):
        assert ROUTE_POLICIES[endpoint].resolver == "grading_config_record"


def test_application_utility_route_family_is_explicitly_public():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source == "app.py"]
    assert len(family) == 13
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in {row.name for row in family}:
        policy = ROUTE_POLICIES[endpoint]
        assert policy.mode is EndpointMode.PUBLIC
        assert policy.action is Action.PUBLIC_VIEW


def test_final_admin_scope_sensitive_slice_is_classified_and_exact():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    admin_rows = [
        row
        for row in rows
        if row.kind == "http"
        and row.name
        in {
            "admin.sensitive_operations_audit",
            "admin.sensitive_operation_details",
            "admin.s3_sync_dashboard",
            "admin.s3_sync_hospital_detail",
            "admin.s3_sync_status_api",
            "admin.s3_sync_stats_api",
            "admin.s3_sync_retry",
            "admin.task_backfill_admin",
            "admin.task_backfill_run",
        }
    ]
    assert len(admin_rows) == 9
    assert {row.classification for row in admin_rows} == {"authz_v2"}
    assert ROUTE_POLICIES["admin.s3_sync_status_api"].resolver == "s3_sync_query"
    assert ROUTE_POLICIES["admin.s3_sync_retry"].resolver == "s3_sync_record"
    assert (
        ROUTE_POLICIES["admin.task_backfill_run"].resolver
        == "task_backfill_target"
    )


def test_remidio_api_configuration_slice_is_classified():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http"
        and row.source == "api/remidio_api_integration.py"
        and row.name
        not in {
            "fundus_api.queue_encounter_set_attachment_ocr",
            "fundus_api.queue_project_pending_encounter_set_attachment_ocr",
            "fundus_api.sync_remidio_api_project",
            "fundus_api.sync_selected_remidio_api_project",
            "fundus_api.pause_remidio_api_project_sync_job",
            "fundus_api.resume_remidio_api_project_sync_job",
            "fundus_api.cancel_remidio_api_project_sync_job",
        }
    ]
    assert len(family) == 25
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "fundus_api.patch_remidio_connection",
        "fundus_api.patch_remidio_site",
        "fundus_api.delete_remidio_api_routing_profile",
        "fundus_api.delete_remidio_api_routing_rule",
    ):
        assert ROUTE_POLICIES[endpoint].resolver == "remidio_config_record"


def test_remidio_api_operational_slice_is_exact_and_method_specific():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http"
        and row.source == "api/remidio_api_integration.py"
    ]
    assert len(family) == 32
    assert {row.classification for row in family} == {"authz_v2"}
    attachment = ROUTE_POLICIES["fundus_api.queue_encounter_set_attachment_ocr"]
    assert attachment["GET"].action is Action.REMIDIO_ATTACHMENT_OCR_VIEW
    assert attachment["POST"].action is Action.REMIDIO_ATTACHMENT_OCR_PROCESS
    project_attachment = ROUTE_POLICIES[
        "fundus_api.queue_project_pending_encounter_set_attachment_ocr"
    ]
    assert project_attachment["GET"].action is Action.PROJECT_REMIDIO_ATTACHMENT_OCR_VIEW
    assert (
        project_attachment["POST"].action
        is Action.PROJECT_REMIDIO_ATTACHMENT_OCR_PROCESS
    )
    assert (
        ROUTE_POLICIES["fundus_api.sync_remidio_api_project"].resolver
        == "remidio_project_sync_target"
    )
    assert ROUTE_POLICIES[
        "fundus_api.pause_remidio_api_project_sync_job"
    ].resolver == "job"


def test_grading_workbench_session_slice_is_credential_bound():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    classified = [
        row
        for row in rows
        if row.kind == "http"
        and row.source == "api/grading_workbench.py"
        and row.classification == "authz_v2"
    ]
    assert len(classified) == 13
    for endpoint in (
        "fundus_api.get_workbench_session",
        "fundus_api.resume_workbench_session",
        "fundus_api.heartbeat_workbench_session",
        "fundus_api.release_workbench_session",
        "fundus_api.save_workbench_session_draft",
        "fundus_api.submit_workbench_session",
    ):
        assert ROUTE_POLICIES[endpoint].resolver == "workbench_session"
    submit = ROUTE_POLICIES["fundus_api.submit_workbench_session"]
    assert submit.action is Action.GRADING_WORKBENCH_SESSION_SUBMIT


def test_grading_workbench_family_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source == "api/grading_workbench.py"
    ]
    assert len(family) == 13
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "fundus_api.acquire_workbench_session",
        "fundus_api.acquire_linked_followup_workbench_session",
        "fundus_api.acquire_task_workbench_session",
        "fundus_api.acquire_package_workbench_session",
        "fundus_api.acquire_revision_workbench_session",
    ):
        assert (
            ROUTE_POLICIES[endpoint].resolver == "workbench_acquisition_target"
        )
    assert (
        ROUTE_POLICIES["fundus_api.acquire_revision_workbench_session"].action
        is Action.GRADING_WORKBENCH_REVISION_ACQUIRE
    )


def test_high_risk_media_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    media_rows = [
        row for row in rows if row.kind == "http" and row.source == "media/routes.py"
    ]
    assert len(media_rows) == 17
    assert {row.classification for row in media_rows} == {"authz_v2"}
    assert all(row.canonical_actions for row in media_rows)


def test_high_risk_grading_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    grading_rows = [
        row for row in rows if row.kind == "http" and row.source.startswith("grading/")
    ]
    assert len(grading_rows) == 30
    assert {row.classification for row in grading_rows} == {"authz_v2"}
    assert all(row.canonical_actions for row in grading_rows)


def test_high_risk_verification_slices_have_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    verification_rows = [
        row
        for row in rows
        if row.kind == "http"
        and row.source.startswith(("verify_encounter_set/", "verify_remedio/"))
    ]
    assert len(verification_rows) == 30
    assert {row.classification for row in verification_rows} == {"authz_v2"}


def test_high_risk_mobile_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    mobile_rows = [
        row
        for row in rows
        if row.kind == "http" and row.source.startswith("api/mobile/")
    ]
    assert len(mobile_rows) == 27
    assert {row.classification for row in mobile_rows} == {"authz_v2"}
    assert all(row.canonical_actions for row in mobile_rows)


def test_high_risk_remidio_upload_workspace_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source.startswith("remidio_api_uploads/")
    ]
    assert len(family) == 13
    assert {row.classification for row in family} == {"authz_v2"}
    assert all(row.canonical_actions for row in family)


def test_high_risk_direct_upload_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source.startswith("direct_uploads/")
    ]
    assert len(family) == 13
    assert {row.classification for row in family} == {"authz_v2"}
    assert all(row.canonical_actions for row in family)


def test_direct_upload_mixed_routes_separate_get_from_post_authority():
    dashboard = ROUTE_POLICIES["direct_uploads.dashboard"]
    edit = ROUTE_POLICIES["direct_uploads.edit_upload"]
    pregraded = ROUTE_POLICIES["direct_uploads.pregraded_upload"]
    grades = ROUTE_POLICIES["direct_uploads.pregraded_grades"]

    assert set(dashboard) == {"GET", "POST"}
    assert dashboard["GET"].mode is EndpointMode.SCREEN
    assert dashboard["POST"].resolver == "direct_upload_batch"
    assert edit["GET"].action.value == "verification.direct.view"
    assert edit["POST"].action.value == "upload.direct.update"
    for policies in (pregraded, grades):
        assert policies["GET"].mode is EndpointMode.SCREEN
        assert policies["POST"].action.value == "upload.pregraded.create"
        assert policies["POST"].resolver == "upload_target"


def test_upload_profile_governance_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source == "api/upload_profiles.py"
    ]
    assert len(family) == 15
    assert {row.classification for row in family} == {"authz_v2"}
    assert all(row.canonical_actions for row in family)


def test_project_role_grant_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source == "api/project_role_grants.py"
    ]
    assert len(family) == 2
    assert {row.classification for row in family} == {"authz_v2"}


def test_admin_user_security_read_slice_is_classified():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    names = {
        "admin.manage_roles",
        "admin.role_usage",
        "admin.routes_by_role",
        "admin.users_list",
        "admin.user_created",
        "admin.user_detail",
        "fundus_api.api_admin_users_activity",
    }
    family = [row for row in rows if row.kind == "http" and row.name in names]
    assert len(family) == len(names) == 7
    assert {row.classification for row in family} == {"authz_v2"}


def test_admin_user_mutations_are_exact_and_method_specific():
    names = {
        "admin.add_user",
        "admin.change_password",
        "admin.edit_user",
        "admin.users_update",
        "admin.revoke_mobile_session",
        "admin.issue_device_enrolment_code",
        "admin.update_mobile_device_status",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.name in names]
    assert len(family) == len(names) == 7
    assert {row.classification for row in family} == {"authz_v2"}

    for endpoint in ("admin.add_user", "admin.change_password", "admin.edit_user"):
        policy = ROUTE_POLICIES[endpoint]
        assert isinstance(policy, dict)
        assert policy["GET"].mode is EndpointMode.SCREEN or (
            endpoint == "admin.edit_user"
            and policy["GET"].mode is EndpointMode.PROTECTED
        )
        assert policy["POST"].mode is EndpointMode.PROTECTED


def test_admin_system_status_and_scanner_slice_is_classified():
    sources = {
        "admin/status.py",
        "admin/cve_scanner.py",
        "admin/package_updates.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 21
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "admin.api_cve_refresh",
        "admin.api_package_updates_refresh",
        "admin.refresh_sequences",
    ):
        policy = ROUTE_POLICIES[endpoint]
        assert policy.mode is EndpointMode.PROTECTED
        assert policy.resolver == "system_operation"


def test_admin_maintenance_and_metadata_slice_is_classified():
    sources = {
        "admin/thumbnail_management.py",
        "admin/materialized_view_status.py",
        "admin/image_metadata.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 24
    assert {row.classification for row in family} == {"authz_v2"}
    mutation_actions = {
        ROUTE_POLICIES[row.name].action
        for row in family
        if "POST" in row.methods
    }
    assert mutation_actions == {
        Action.ADMIN_SYSTEM_OPERATION,
        Action.ADMIN_STORAGE_OPERATION,
        Action.ADMIN_METADATA_OPERATION,
    }


def test_admin_configuration_slice_is_classified_and_method_specific():
    sources = {
        "admin/email_settings.py",
        "admin/s3_config.py",
        "admin/app_settings.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 20
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "admin.create_email_settings",
        "admin.s3_config_create",
        "admin.s3_config_edit",
        "admin.admin_settings",
        "admin.upload_settings",
    ):
        policy = ROUTE_POLICIES[endpoint]
        assert isinstance(policy, dict)
        assert policy["POST"].mode is EndpointMode.PROTECTED


def test_admin_database_movement_slice_is_classified_and_exact():
    sources = {
        "admin/database_dump.py",
        "admin/database_excel_export.py",
        "admin/database_restore.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 8
    assert {row.classification for row in family} == {"authz_v2"}
    assert ROUTE_POLICIES["admin.database_dump"]["POST"].action is (
        Action.ADMIN_DATABASE_EXPORT
    )
    for endpoint in (
        "admin.database_restore.upload_file",
        "admin.database_restore.restore_database",
        "admin.database_restore.cancel_restore",
    ):
        policy = ROUTE_POLICIES[endpoint]
        assert policy.action is Action.ADMIN_DATABASE_RESTORE
        assert policy.mode is EndpointMode.PROTECTED


def test_admin_operational_storage_slice_is_classified():
    sources = {
        "admin/logs.py",
        "admin/uploads.py",
        "admin/disk_usage.py",
        "admin/upload_quotas.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 8
    assert {row.classification for row in family} == {"authz_v2"}
    quota = ROUTE_POLICIES["admin.update_upload_quota"]
    assert quota.action is Action.ADMIN_UPLOAD_QUOTA_MANAGE
    assert quota.resolver == "user"
    for endpoint in ("admin.delete_duplicates", "admin.delete_old_processed_zips"):
        assert ROUTE_POLICIES[endpoint].action is Action.ADMIN_SYSTEM_OPERATION


def test_admin_lookup_governance_slice_is_classified_and_exact():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [
        row
        for row in rows
        if row.kind == "http" and row.source.startswith("admin/lookups/")
    ]
    assert len(family) == 15
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "admin.edit_hospital",
        "admin.edit_lab_unit",
        "admin.edit_disease",
        "admin.edit_camera",
        "admin.edit_area",
    ):
        policy = ROUTE_POLICIES[endpoint]
        assert isinstance(policy, dict)
        assert policy["GET"].action is Action.ADMIN_LOOKUP_RECORD_VIEW
        assert policy["POST"].action is Action.ADMIN_LOOKUP_RECORD_MANAGE


def test_admin_grading_configuration_slice_is_classified():
    sources = {
        "admin/disease_gradings.py",
        "admin/linked_grading.py",
        "admin/grading_schemes.py",
        "admin/encounter_set_types.py",
        "admin/grading_eligibility.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 20
    assert {row.classification for row in family} == {"authz_v2"}
    eligibility = ROUTE_POLICIES["admin.edit_eligibility"]
    assert isinstance(eligibility, dict)
    assert eligibility["POST"].action is (
        Action.ADMIN_GRADING_ELIGIBILITY_USER_MANAGE
    )
    assert eligibility["POST"].resolver == "user"


def test_admin_remidio_operations_slice_is_classified():
    sources = {
        "admin/remidio.py",
        "admin/remidio_encounter_migration.py",
        "admin/iitk.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 9
    assert {row.classification for row in family} == {"authz_v2"}
    cleanup = ROUTE_POLICIES["admin.cleanup_stuck_remidio_uploads"]
    assert cleanup.action is Action.ADMIN_SYSTEM_OPERATION
    assert cleanup.mode is EndpointMode.PROTECTED


def test_admin_executable_configuration_slice_is_classified():
    sources = {"admin/ai_models.py", "admin/celery_schedule.py"}
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 8
    assert {row.classification for row in family} == {"authz_v2"}
    for endpoint in (
        "admin.edit_ai_model",
        "admin.list_and_create_ai_model",
    ):
        assert isinstance(ROUTE_POLICIES[endpoint], dict)
    for endpoint in (
        "admin.delete_ai_model",
        "admin.test_ai_model_health",
        "admin.celery_schedule_update",
        "admin.celery_schedule_delete",
    ):
        policy = ROUTE_POLICIES[endpoint]
        assert policy.action is Action.ADMIN_EXECUTABLE_CONFIG_MANAGE
        assert policy.resolver == "executable_config_record"


def test_admin_grading_repair_slice_is_classified_and_exact():
    sources = {
        "admin/task_review_inconsistency.py",
        "admin/grading_state_inconsistencies.py",
        "admin/linked_task_inconsistencies.py",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.source in sources]
    assert len(family) == 4
    assert {row.classification for row in family} == {"authz_v2"}
    assert ROUTE_POLICIES["admin.apply_review_as_final"].resolver == (
        "grading_repair_target"
    )
    mixed = ROUTE_POLICIES["admin.grading_state_inconsistencies"]
    assert isinstance(mixed, dict)
    assert mixed["GET"].mode is EndpointMode.SCREEN
    assert mixed["POST"].resolver == "grading_repair_batch"


def test_admin_global_rate_limit_and_upload_config_slice_is_classified():
    names = {
        "rate_limit_admin.index",
        "rate_limit_admin.status",
        "rate_limit_admin.get_my_key",
        "rate_limit_admin.clear_limit",
        "rate_limit_admin.clear_limit_ajax",
        "rate_limit_admin.clear_all",
        "admin.upload_profiles_admin",
        "admin.upload_project_create_workspace",
        "admin.upload_projects_admin",
        "admin.upload_project_workspace",
        "admin.upload_metadata_fields_admin",
        "admin.upload_metadata_fields_list",
    }
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    family = [row for row in rows if row.kind == "http" and row.name in names]
    assert len(family) == len(names) == 12
    assert {row.classification for row in family} == {"authz_v2"}
    assert ROUTE_POLICIES["admin.upload_project_workspace"].resolver == "project"
    for endpoint in (
        "rate_limit_admin.clear_limit",
        "rate_limit_admin.clear_limit_ajax",
        "rate_limit_admin.clear_all",
    ):
        assert ROUTE_POLICIES[endpoint].action is Action.ADMIN_SYSTEM_OPERATION


def test_mobile_route_contracts_separate_public_signed_and_access_token_channels():
    mobile = {
        endpoint: policy
        for endpoint, policy in ROUTE_POLICIES.items()
        if endpoint.startswith("mobile_api.")
    }
    assert len(mobile) == 27
    assert mobile["mobile_api.login"].mode is EndpointMode.PUBLIC
    assert {
        mobile["mobile_api.refresh"].mode,
        mobile["mobile_api.logout"].mode,
    } == {EndpointMode.SIGNED_RESOURCE}
    assert all(
        policy.mode is EndpointMode.MOBILE_SESSION
        for endpoint, policy in mobile.items()
        if endpoint
        not in {"mobile_api.login", "mobile_api.refresh", "mobile_api.logout"}
    )
    assert mobile["mobile_api.refresh"].resolver == "mobile_session"
    assert mobile["mobile_api.logout"].resolver == "mobile_session"


def test_every_inventory_row_has_a_traceable_runtime_identity():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    assert all(row.name and row.source and row.line for row in rows)
    identities = [(row.kind, row.name, row.methods, row.path) for row in rows]
    assert len(identities) == len(set(identities))


def test_every_catalogued_endpoint_is_registered_in_the_live_app():
    app = create_app()
    live_endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert set(ROUTE_POLICIES) <= live_endpoints
