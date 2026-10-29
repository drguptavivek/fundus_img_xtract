from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from flask import Flask

from api import encounter_set_exports
from authz.exceptions import AuthorizationDenied


@pytest.mark.parametrize(
    ("view", "reason", "expected"),
    [
        ("export_encounter_sets", "admin_required,project_role_scope_missing", "data_exporter or pii_exporter"),
        ("export_encounter_sets_pii", "admin_required,project_role_scope_missing", "pii_exporter"),
        ("export_encounter_sets", "export_lab_unit_unauthorized", "selected lab unit"),
        ("export_encounter_sets_pii", "classical_pii_export_requires_admin", "without a project require an administrator"),
    ],
)
def test_export_authorization_denial_is_actionable_json(monkeypatch, view, reason, expected):
    app = Flask(__name__)
    monkeypatch.setattr(encounter_set_exports, "current_user", SimpleNamespace(timezone="UTC"))
    monkeypatch.setattr(encounter_set_exports, "get_db_session", lambda: nullcontext(None))

    def deny(*args, **kwargs):
        raise AuthorizationDenied(reason)

    monkeypatch.setattr(encounter_set_exports, "export_encounter_sets_xlsx", deny)
    handler = getattr(encounter_set_exports, view)
    while hasattr(handler, "__wrapped__"):
        handler = handler.__wrapped__
    with app.test_request_context("/?project_id=3&month=2026-10"):
        response, status = handler()
    assert status == 403
    assert expected in response.get_json()["error"]
    if "project_role_scope_missing" in reason:
        assert "lab_unit_id" in response.get_json()["error"]
