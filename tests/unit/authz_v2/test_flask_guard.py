import pytest
from flask import Flask, jsonify

from authz_v2.core.actions import Action
from authz_v2.core.catalogue import CATALOGUE
from authz_v2.flask import EndpointMode, authorization_endpoint, install_default_deny
from authz_v2.flask.hooks import unclassified_endpoints
from authz_v2.flask.manifest import build_route_manifest
from authz_v2.telemetry.metrics import snapshot


def test_unclassified_endpoint_denies_before_handler_execution():
    app = Flask(__name__)
    called = []

    @app.get("/unclassified")
    def unclassified():
        called.append(True)
        return "unsafe"

    install_default_deny(app, authenticated=lambda: True)
    before = snapshot().get(("authz_unclassified_endpoint_total", "", ""), 0)
    response = app.test_client().get("/unclassified")
    assert response.status_code == 403
    assert response.get_json() == {"error": "not_authorized"}
    assert called == []
    assert unclassified_endpoints(app) == ("unclassified",)
    assert snapshot()[("authz_unclassified_endpoint_total", "", "")] == before + 1


def test_exact_public_and_authenticated_screen_classifications():
    app = Flask(__name__)
    authenticated = False

    @app.get("/public")
    @authorization_endpoint(EndpointMode.PUBLIC, Action.PUBLIC_VIEW)
    def public():
        return jsonify(ok=True)

    @app.get("/screen")
    @authorization_endpoint(
        EndpointMode.SCREEN,
        Action.DASHBOARD_VIEW,
        enforcement="screen_entry",
    )
    def screen():
        return jsonify(ok=True)

    install_default_deny(app, authenticated=lambda: authenticated)
    client = app.test_client()
    assert client.get("/public").status_code == 200
    assert client.get("/screen").status_code == 403
    authenticated = True
    assert client.get("/screen").status_code == 200
    assert unclassified_endpoints(app) == ()


def test_protected_endpoint_requires_named_resource_resolver():
    try:
        authorization_endpoint(EndpointMode.PROTECTED, Action.ACCOUNT_PROFILE_VIEW)
    except ValueError as error:
        assert "exact resource resolver" in str(error)
    else:
        raise AssertionError("protected endpoint accepted without resolver")
    with pytest.raises(ValueError, match="catalogue resource type"):
        authorization_endpoint(
            EndpointMode.PROTECTED,
            Action.ACCOUNT_PROFILE_VIEW,
            resolver="project",
        )
    with pytest.raises(ValueError):
        authorization_endpoint(EndpointMode.PUBLIC, Action.DASHBOARD_VIEW)


@pytest.mark.parametrize(
    ("mode", "action"),
    [
        (EndpointMode.SIGNED_RESOURCE, Action.AUTH_PASSWORD_RESET_COMPLETE),
        (EndpointMode.MOBILE_SESSION, Action.MOBILE_FIELD_ENCOUNTER_VIEW),
        (EndpointMode.AUTOMATION, Action.INFERENCE_WAI_RUN),
    ],
)
def test_exact_non_web_modes_require_resolver_and_matching_channel(mode, action):
    with pytest.raises(ValueError, match="exact resource resolver"):
        authorization_endpoint(mode, action)
    authorization_endpoint(mode, action, resolver=CATALOGUE[action].resource_type)

    with pytest.raises(ValueError, match="session channel"):
        authorization_endpoint(mode, Action.ACCOUNT_PROFILE_VIEW, resolver="user")


def test_dynamic_endpoint_binding_declares_and_enforces_an_action_allowlist():
    app = Flask(__name__)

    @app.get("/media/<uuid_str>")
    @authorization_endpoint(
        EndpointMode.SIGNED_RESOURCE,
        Action.MEDIA_IMAGE_VIEW,
        action_variants=(Action.MEDIA_PDF_VIEW,),
        binding="media_source",
    )
    def media(uuid_str):
        return uuid_str

    manifest = build_route_manifest(app)[0]
    assert manifest.actions == ("media.image.view", "media.pdf.view")
    assert manifest.binding == "media_source"
    assert manifest.resource_types == ("image", "encounter_file")

    with pytest.raises(ValueError, match="dynamic endpoint binding requires"):
        authorization_endpoint(
            EndpointMode.SIGNED_RESOURCE,
            Action.MEDIA_IMAGE_VIEW,
            binding="media_source",
        )


def test_route_manifest_projects_catalogue_security_metadata():
    app = Flask(__name__)

    @app.get("/screen")
    @authorization_endpoint(
        EndpointMode.SCREEN,
        Action.DASHBOARD_VIEW,
        enforcement="screen_entry",
    )
    def screen():
        return "ok"

    @app.get("/unclassified")
    def unclassified():
        return "unsafe"

    manifest = {row.endpoint: row for row in build_route_manifest(app)}
    assert manifest["screen"].action == Action.DASHBOARD_VIEW.value
    assert manifest["screen"].resource_type == "screen"
    assert manifest["screen"].disclosure_class == "masked"
    assert manifest["screen"].methods == ("GET",)
    assert manifest["unclassified"].action is None
