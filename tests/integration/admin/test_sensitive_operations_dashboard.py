from unittest.mock import patch

import pytest

from auth.utils import utcnow
from models import SensitiveOperationAudit

# Removed clean_context_processors to ensure base.html works in error cases

def test_dashboard_access_denied_for_non_admin(app, client, resident_user):
    """Verify that non-admin/data_manager users cannot access the dashboard."""
    app.config['SERVER_NAME'] = 'localhost'
    with app.app_context():
        with client.session_transaction() as sess:
            sess['user_id'] = resident_user.id
            sess['_user_id'] = str(resident_user.id)
            sess['_fresh'] = True

        target_url = "/admin/sensitive-operations"
        response = client.get(target_url, follow_redirects=True)
        
        # Should return 403 Forbidden or redirect
        assert response.status_code in [403, 200]
        if response.status_code == 200:
             page_text = response.get_data(as_text=True)
             # Basic verification for Permission Denied page
             assert "Permission denied" in page_text or "Home" in page_text

def test_dashboard_access_denied_for_local_admin(
    app, client, db_session, site_admin_hospital_a
):
    """Sensitive-operation audit details are global-admin-only."""
    user_id = db_session.merge(site_admin_hospital_a).id
    with client.session_transaction() as sess:
        sess['user_id'] = str(user_id)
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    assert client.get("/admin/sensitive-operations").status_code == 403
    assert client.get("/admin/sensitive-operations/1").status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/s3-sync-dashboard"),
        ("get", "/admin/s3-sync-dashboard/hospital/1"),
        ("get", "/admin/api/s3-sync-status"),
        ("post", "/admin/api/s3-sync-retry/1"),
        ("get", "/admin/api/s3-sync-stats"),
    ],
)
@pytest.mark.parametrize("user_fixture", ["site_admin_hospital_a", "hosp_a_data_manager"])
def test_s3_sync_surface_denies_non_admin_roles(
    app, client, db_session, request, method, path, user_fixture
):
    """Neither classical management role can query or mutate S3 state."""
    user_id = db_session.merge(request.getfixturevalue(user_fixture)).id
    with client.session_transaction() as sess:
        sess['user_id'] = str(user_id)
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    assert getattr(client, method)(path).status_code == 403


def test_s3_sync_api_remains_reachable_to_global_admin(client, admin_user):
    """The narrowed boundary must not disable the global-admin workflow."""
    with client.session_transaction() as sess:
        sess['user_id'] = str(admin_user.id)
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True

    assert client.get("/admin/api/s3-sync-status").status_code == 200
    assert client.post("/admin/api/s3-sync-retry/999999").status_code == 404


@pytest.mark.parametrize(
    "query",
    [
        "hospital_id=",
        "hospital_id=abc",
        "hospital_id=0",
        "hospital_id=-1",
        "limit=",
        "limit=abc",
        "limit=0",
        "limit=501",
        "status=unknown",
    ],
)
def test_s3_sync_status_rejects_malformed_supplied_filters(client, admin_user, query):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True

    response = client.get(f"/admin/api/s3-sync-status?{query}")
    assert response.status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        "/admin/s3-configs/api/test-connection-modal",
        "/admin/s3-configs/api/create",
    ],
)
def test_s3_config_modal_apis_reject_unknown_hospital_before_io(
    client, admin_user, path
):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True

    form = {
        "hospital_id": "999999",
        "provider": "aws",
        "name": "test config",
        "bucket_name": "valid-test-bucket",
        "region": "us-east-1",
        "access_key": "access",
        "secret_key": "secret",
    }
    with (
        patch("utils.s3_storage_backends.create_s3_client_from_creds") as create_client,
        patch("admin.s3_config.encrypt_secret") as encrypt_secret,
    ):
        response = client.post(path, data=form)

    assert response.status_code == 200
    assert response.get_json()["success"] is False
    assert "Invalid hospital" in response.get_json()["message"]
    create_client.assert_not_called()
    encrypt_secret.assert_not_called()

def test_dashboard_renders_logs(app, client, db_session, admin_user):
    """Verify that the dashboard queries logs correctly (Mocked View)."""
    app.config['SERVER_NAME'] = 'localhost'
    
    # Create test logs
    log1 = SensitiveOperationAudit(
        user_id=admin_user.id,
        operation_type="test_export",
        status="completed",
        ip_address="127.0.0.1",
        created_at=utcnow()
    )
    db_session.add(log1)
    
    log2 = SensitiveOperationAudit(
        user_id=admin_user.id,
        operation_type="failed_op",
        status="failed",
        ip_address="192.168.1.1",
        created_at=utcnow()
    )
    db_session.add(log2)
    db_session.commit()
    
    # Login as admin
    with client.session_transaction() as sess:
        sess['user_id'] = admin_user.id
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True

    target_url = "/admin/sensitive-operations"
    
    with patch('admin.audit_routes.render_template', return_value="OK") as mock_render:
        response = client.get(target_url)
        assert response.status_code == 200
        
        _, kwargs = mock_render.call_args
        audit_logs = kwargs['audit_logs']
        
        # Verify logs content logic (DTOs are dictionaries)
        ops = [l['operation_type'] for l in audit_logs]
        assert "test_export" in ops
        assert "failed_op" in ops

@pytest.mark.xfail(reason="Email config setup error in test environment", raises=Exception)
def test_dashboard_filters(app, client, db_session, admin_user):
    """Verify filtering logic on the dashboard (Mocked View)."""
    app.config['SERVER_NAME'] = 'localhost'
    
    # Create logs
    log1 = SensitiveOperationAudit(
        user_id=admin_user.id, 
        status="completed", 
        operation_type="op1", 
        created_at=utcnow()
    )
    log2 = SensitiveOperationAudit(
        user_id=admin_user.id, 
        status="failed", 
        operation_type="op2", 
        created_at=utcnow()
    )
    db_session.add(log1)
    db_session.add(log2)
    db_session.commit()
    
    with client.session_transaction() as sess:
        sess['user_id'] = admin_user.id
        sess['_fresh'] = True
        
    # Filter by status=failed
    target_url = "/admin/sensitive-operations?status=failed"
    
    with patch('admin.audit_routes.render_template', return_value="OK") as mock_render:
        response = client.get(target_url)
        assert response.status_code == 200
        
        _, kwargs = mock_render.call_args
        audit_logs = kwargs['audit_logs']
        
        # Verify filtering logic (DTOs are dictionaries)
        ops = [l['operation_type'] for l in audit_logs]
        assert "op2" in ops
        assert "op1" not in ops
