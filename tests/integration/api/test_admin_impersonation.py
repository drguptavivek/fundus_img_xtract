from models import SensitiveOperationAudit, User


def _authenticate(client, user_id: int) -> str:
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    response = client.get("/")
    html = response.get_data(as_text=True)
    marker = '<meta name="csrf-token" content="'
    return html.split(marker, 1)[1].split('"', 1)[0]


def test_admin_can_start_and_stop_impersonation(client, db_session, admin_user, core_test_data):
    target = db_session.query(User).filter_by(username="test_manager").one()
    csrf = _authenticate(client, admin_user.id)

    users_page = client.get("/admin/users")
    assert users_page.status_code == 200
    assert b"/static/js/htmx.min.js" in users_page.data
    assert b"/static/js/admin-impersonation.js" in users_page.data
    assert b"-impersonation-v2" in users_page.data
    assert f'data-impersonate-user-id="{target.id}"'.encode() in users_page.data
    impersonation_js = client.get("/static/js/admin-impersonation.js")
    assert impersonation_js.status_code == 200
    assert b"}, true);" in impersonation_js.data

    started = client.post(
        "/api/admin/impersonation",
        json={"user_id": target.id},
        headers={"X-CSRFToken": csrf},
    )
    assert started.status_code == 200
    assert started.get_json()["data"]["effective_user"]["id"] == target.id
    with client.session_transaction() as sess:
        assert sess["_user_id"] == str(target.id)
        assert sess["impersonation_original_user_id"] == admin_user.id

    page = client.get("/")
    assert b"Impersonating test_manager" in page.data
    assert b"Read-only session" in page.data
    csrf = page.get_data(as_text=True).split('<meta name="csrf-token" content="', 1)[1].split('"', 1)[0]
    nested = client.post(
        "/api/admin/impersonation",
        json={"user_id": target.id},
        headers={"X-CSRFToken": csrf},
    )
    assert nested.status_code == 403
    assert nested.get_json()["error"].startswith("Impersonation is read-only")
    stopped = client.delete(
        "/api/admin/impersonation",
        headers={"X-CSRFToken": csrf},
    )
    assert stopped.status_code == 200
    with client.session_transaction() as sess:
        assert sess["_user_id"] == str(admin_user.id)
        assert "impersonation_original_user_id" not in sess

    audits = db_session.query(SensitiveOperationAudit).filter_by(
        user_id=admin_user.id,
        operation_type="user_impersonation",
    ).order_by(SensitiveOperationAudit.id).all()
    assert [audit.status for audit in audits[-2:]] == ["started", "stopped"]
    assert audits[-1].get_request_details()["target_user_id"] == target.id


def test_non_admin_cannot_impersonate(client, db_session, core_test_data):
    actor = db_session.query(User).filter_by(username="test_manager").one()
    target = db_session.query(User).filter_by(username="ophthalmologist_a").one()
    csrf = _authenticate(client, actor.id)

    response = client.post(
        "/api/admin/impersonation",
        json={"user_id": target.id},
        headers={"X-CSRFToken": csrf},
    )
    assert response.status_code == 403
    with client.session_transaction() as sess:
        assert sess["_user_id"] == str(actor.id)


def test_admin_cannot_impersonate_an_admin(client, db_session, admin_user, core_test_data):
    target = db_session.query(User).filter_by(username="master_admin").one()
    csrf = _authenticate(client, admin_user.id)

    response = client.post(
        "/api/admin/impersonation",
        json={"user_id": target.id},
        headers={"X-CSRFToken": csrf},
    )
    assert response.status_code == 403


def test_impersonation_mutations_require_csrf(app, client, db_session, admin_user, core_test_data):
    target = db_session.query(User).filter_by(username="test_manager").one()
    prior_setting = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        _authenticate(client, admin_user.id)
        response = client.post("/api/admin/impersonation", json={"user_id": target.id})
        assert response.status_code == 400
    finally:
        app.config["WTF_CSRF_ENABLED"] = prior_setting
