import json
import subprocess
import sys

from app import create_app
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
        "authz_v2": 145,
        "legacy_action_literal": 46,
        "legacy_unmapped": 489,
        "automation_unmapped": 47,
        "query_candidate_unmapped": 978,
    }
    assert (
        inventory["identity_fingerprint"]
        == "00962d43705fd54ce0e2b2cfe33cb128232574bb16d7871cb57c00fb28c12c64"
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
