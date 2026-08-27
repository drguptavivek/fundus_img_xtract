from types import SimpleNamespace

from flask import Flask, jsonify

from authz_v2.core.actions import Action
from authz_v2.flask import EndpointMode, authorization_endpoint, install_default_deny


class Service:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def require(self, db, principal, action, resource, *, audit_service=None):
        self.calls.append((db, principal, action, resource, audit_service))
        if not self.allowed:
            raise PermissionError("not_authorized")
        return SimpleNamespace(action=action.value, resource_id=resource)


def _app(service, resolver):
    app = Flask(__name__)

    @app.get("/users/<int:user_id>")
    @authorization_endpoint(
        EndpointMode.PROTECTED,
        Action.ACCOUNT_PROFILE_VIEW,
        resolver="user",
    )
    def view_user(user_id):
        return jsonify(user_id=user_id)

    install_default_deny(
        app,
        authenticated=lambda: True,
        principal=lambda: "principal",
        database=lambda: "db",
        decision_service=lambda _db: service,
        resource_resolvers={"user": resolver},
    )
    return app


def test_decorated_handler_cannot_run_without_central_allow_decision():
    denied = Service(False)
    response = (
        _app(denied, lambda values: values.get("user_id")).test_client().get("/users/7")
    )
    assert response.status_code == 403
    allowed = Service(True)
    response = (
        _app(allowed, lambda values: values.get("user_id"))
        .test_client()
        .get("/users/7")
    )
    assert response.status_code == 200
    assert allowed.calls[0][3] == 7


def test_missing_authorization_resource_fails_before_handler():
    response = _app(Service(True), lambda _values: None).test_client().get("/users/7")
    assert response.status_code == 403
