"""Human review dashboard: access boundaries, filters and durable audit data."""
import pytest

from project_sync.audit import AuditFilter, record_sync_request, review_sync_audit
from project_sync.exceptions import ProjectSyncPermissionDenied, ProjectSyncValidationError
from tests.unit.project_sync.test_project_sync import world, sync_on, _approved_credential, _no_shared_redis
from tests.conftest import create_authenticated_client


def test_activity_admin_api_and_standalone_partial(app, db_session, world):
    from project_sync.dto import SyncContext
    context = SyncContext(1, "review-grant", world["dm"].id, world["dm"].username,
                          world["project"].id, world["project"].code, frozenset({world["lab_a1"].id}))
    record_sync_request(db_session, context=context, ip_address="10.2.3.4", user_agent="desktop-review",
                        endpoint="project_sync_api.encounters", method="GET", http_status=200,
                        response_bytes=1234, duration_ms=12)
    db_session.flush()
    admin = create_authenticated_client(app, world["admin"], db_session)
    url = "/api/project-sync/admin/activity"
    response = admin.get(url, query_string={"project_id": world["project"].id, "ip_address": "10.2.3.4"})
    assert response.status_code == 200, response.json
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json["total_events"] == 1
    row = response.json["events"][0]
    assert row["username"] == world["dm"].username
    assert row["project_code"] == "SYNC_P"
    assert row["response_bytes"] == 1234
    assert admin.get(url, query_string={"ip_address": "10.9.9.9"}).json["events"] == []
    assert admin.get(url, query_string={"username": world["outsider"].username}).json["events"] == []
    page = admin.get("/project-sync/admin/activity")
    assert page.status_code == 200 and b"Project Sync Activity" in page.data
    app.config["WTF_CSRF_ENABLED"] = True
    partial = admin.get(url, headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert b'name="csrf_token"' in partial.data
    assert b"desktop-review" in partial.data
    assert b"sync-activity-workspace" in partial.data


def test_activity_denies_non_admin_and_anonymous(app, db_session, world):
    user = create_authenticated_client(app, world["dm"], db_session)
    for path in ("/project-sync/admin/activity", "/api/project-sync/admin/activity"):
        assert user.get(path).status_code == 403
        assert app.test_client().get(path).status_code in {302, 401, 403}
    with pytest.raises(ProjectSyncPermissionDenied):
        review_sync_audit(db_session, admin=world["dm"], filters=AuditFilter.parse())


@pytest.mark.parametrize("arguments", [
    {"since": "bad"}, {"since": "2026-01-01", "until": "2026-03-01"},
    {"since": "2026-02-01", "until": "2026-01-01"}, {"ip_address": "injected text"},
    {"project_id": "-1"}, {"before_id": "bad"},
])
def test_activity_filters_reject_invalid_values(arguments):
    with pytest.raises(ProjectSyncValidationError):
        AuditFilter.parse(**arguments)


def test_sync_access_is_persisted_without_patient_or_credential_data(sync_on, client, db_session, world):
    from models import SensitiveOperationAudit
    _, credential = _approved_credential(db_session, world, world["dm"])
    response = client.get("/api/sync/v1/encounters", headers={"Authorization": f"Bearer {credential}"})
    assert response.status_code == 200
    row = db_session.query(SensitiveOperationAudit).filter_by(operation_type="project_sync_request").order_by(SensitiveOperationAudit.id.desc()).first()
    assert row.user_id == world["dm"].id
    assert row.get_request_details()["project_id"] == world["project"].id
    assert row.get_result_details()["http_status"] == 200
    assert credential not in row.request_details
    assert "Jane Patient" not in row.request_details


def test_activity_cursor_is_bounded(app, db_session, world):
    from project_sync.audit import PAGE_SIZE
    for _ in range(PAGE_SIZE + 1):
        record_sync_request(db_session, context=None, ip_address="10.2.3.4", user_agent="test",
                            endpoint="project_sync_api.whoami", method="GET", http_status=401,
                            response_bytes=0, duration_ms=1)
    db_session.flush()
    first = review_sync_audit(db_session, admin=world["admin"], filters=AuditFilter.parse())
    assert len(first.events) == PAGE_SIZE and first.next_before_id is not None
    second = review_sync_audit(db_session, admin=world["admin"], filters=AuditFilter.parse(before_id=first.next_before_id))
    assert len(second.events) == 1 and second.next_before_id is None
    assert not ({event.id for event in first.events} & {event.id for event in second.events})


def test_sync_audit_failure_refuses_data_and_releases_slot(sync_on, client, db_session, world, monkeypatch, _no_shared_redis):
    from api.sync import routes
    _, credential = _approved_credential(db_session, world, world["dm"])
    def unavailable(*args, **kwargs):
        raise RuntimeError("test audit unavailable")
    monkeypatch.setattr(routes, "record_sync_request", unavailable)
    response = client.get("/api/sync/v1/encounters", headers={"Authorization": f"Bearer {credential}"})
    assert response.status_code == 503
    assert response.json["error"] == "audit_unavailable"
    assert _no_shared_redis == ["slot"]
