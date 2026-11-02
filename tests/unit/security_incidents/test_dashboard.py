from datetime import timedelta
from unittest.mock import Mock

import pytest

from auth.utils import utcnow
from security_incidents.geoip import locate_ip
from security_incidents.service import record_ip_ban
from tests.conftest import create_authenticated_client
from tests.unit.project_sync.test_project_sync import world


def test_geoip_is_offline_and_labels_unknown_sources(tmp_path, monkeypatch):
    from security_incidents import geoip
    assert locate_ip("10.0.0.1", database_path=None).status == "private_or_reserved"
    assert locate_ip("8.8.8.8", database_path=None).status == "not_configured"
    assert locate_ip("bad", database_path=None).status == "invalid"
    assert locate_ip("8.8.8.8", database_path="/missing.mmdb").status == "lookup_unavailable"
    path = tmp_path / "geo.mmdb"
    path.write_bytes(b"fixture")
    reader = Mock()
    reader.get.return_value = {"country": {"names": {"en": "Example country"}}, "city": {"names": {"en": "Example city"}}}
    reader.metadata.return_value.build_epoch = 1767225600
    monkeypatch.setattr(geoip, "_reader", lambda *args: reader)
    located = locate_ip("8.8.8.8", database_path=str(path))
    assert located.status == "located" and located.country == "Example country" and located.city == "Example city"
    assert located.database_date


def test_admin_sees_live_ip_and_account_blocks_and_history(app, db_session, world):
    from models import IpLock
    backend = Mock()
    backend.zrevrangebyscore.return_value = [b"8.8.8.8"]
    backend.ttl.return_value = 123
    app.extensions["api_abuse_backend"] = backend
    record_ip_ban(db_session, ip_address="8.8.8.8", endpoint="project_sync_api.media", method="GET")
    until = utcnow() + timedelta(hours=1)
    world["dm"].is_locked_until = until
    db_session.add(IpLock(ip_address="10.0.0.2", locked_until=until))
    db_session.flush()
    admin = create_authenticated_client(app, world["admin"], db_session)
    endpoint = "/api/admin/security/incidents"
    response = admin.get(endpoint)
    assert response.status_code == 200, response.json
    assert response.headers["Cache-Control"] == "no-store"
    assert {row["ip_address"] for row in response.json["active_blocks"]} == {"8.8.8.8", "10.0.0.2"}
    assert response.json["account_locks"][0]["username"] == world["dm"].username
    assert response.json["incidents"][0]["endpoint"] == "project_sync_api.media"
    assert any("CSP migration" == item["control"] for item in response.json["mitigations"])
    assert admin.get("/admin/security/incidents").status_code == 200
    partial = admin.get(endpoint, headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert b"8.8.8.8" in partial.data and b"10.0.0.2" in partial.data
    assert b"security-incidents-workspace" in partial.data


def test_security_dashboard_denies_non_admin(app, db_session, world):
    user = create_authenticated_client(app, world["dm"], db_session)
    for endpoint in ("/admin/security/incidents", "/api/admin/security/incidents"):
        assert user.get(endpoint).status_code == 403


def test_unavailable_block_state_is_not_reported_as_zero(app, db_session, world):
    import redis
    backend = Mock()
    backend.zrevrangebyscore.side_effect = redis.ConnectionError("offline")
    app.extensions["api_abuse_backend"] = backend
    admin = create_authenticated_client(app, world["admin"], db_session)
    assert admin.get("/api/admin/security/incidents").status_code == 503
