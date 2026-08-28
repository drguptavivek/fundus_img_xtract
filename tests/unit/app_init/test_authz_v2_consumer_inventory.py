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
        "authz_v2": 257,
        "legacy_action_literal": 45,
        "legacy_unmapped": 378,
        "automation_unmapped": 47,
        "query_candidate_unmapped": 978,
    }
    assert (
        inventory["identity_fingerprint"]
        == "856341934705047d177e122bbc34616a976ec2b1dba4d552bbe37475eb9c4fcb"
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
