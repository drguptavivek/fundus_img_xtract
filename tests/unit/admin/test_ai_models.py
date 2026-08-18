from models import AIModel, AIModelDisease, AIModelIntegration, Disease


def _glaucoma_id(db_session):
    disease = db_session.query(Disease).filter_by(name="Glaucoma").one()
    return disease.id


def test_create_ai_model_with_wadhwani_binding(client, login_user, db_session):
    login_user("test_admin", "Test@2026")

    response = client.post(
        "/admin/ai-models",
        data={
            "name": "wai_glaucoma_ver1",
            "version": "1.0",
            "description": "Linked glaucoma model",
            "link_to_wadhwani_glaucoma_api": "on",
            "wadhwani_client_id": "client-123",
            "wadhwani_bearer_token": "secret-token",
            "disease_ids": [str(_glaucoma_id(db_session))],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"added successfully" in response.data

    model = db_session.query(AIModel).filter_by(name="wai_glaucoma_ver1", version="1.0").one()
    integration = db_session.query(AIModelIntegration).filter_by(ai_model_id=model.id).one()
    disease_link = db_session.query(AIModelDisease).filter_by(ai_model_id=model.id, disease_id=_glaucoma_id(db_session)).one()

    assert integration.provider == "wadhwani_glaucoma"
    assert integration.client_id == "client-123"
    assert integration.bearer_token == "secret-token"
    assert disease_link.active is True


def test_only_one_ai_model_can_be_linked_to_wadhwani(client, login_user, db_session):
    login_user("test_admin", "Test@2026")

    first_model = AIModel(name="linked_model_one", version="1.0", description="first")
    db_session.add(first_model)
    db_session.flush()
    db_session.add(
        AIModelIntegration(
            ai_model_id=first_model.id,
            provider="wadhwani_glaucoma",
            client_id="client-123",
            bearer_token="secret-token",
        )
    )
    db_session.flush()

    response = client.post(
        "/admin/ai-models",
        data={
            "name": "linked_model_two",
            "version": "1.0",
            "description": "second",
            "link_to_wadhwani_glaucoma_api": "on",
            "wadhwani_client_id": "client-456",
            "wadhwani_bearer_token": "secret-token-2",
            "disease_ids": [str(_glaucoma_id(db_session))],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Only one AI Model can be linked to the Wadhwani Glaucoma API" in response.data

    second_model = db_session.query(AIModel).filter_by(name="linked_model_two", version="1.0").one_or_none()
    assert second_model is None


def test_ai_model_health_returns_upstream_status(client, login_user, db_session, monkeypatch):
    login_user("test_admin", "Test@2026")

    model = AIModel(name="health_model", version="1.0", description="health")
    db_session.add(model)
    db_session.flush()
    db_session.add(
        AIModelIntegration(
            ai_model_id=model.id,
            provider="wadhwani_glaucoma",
            client_id="client-123",
            bearer_token="secret-token",
        )
    )
    db_session.flush()

    class MockResponse:
        status_code = 200
        ok = True
        content = b'{"status":"healthy","model_loaded":true}'

        @staticmethod
        def json():
            return {"status": "healthy", "model_loaded": True}

    monkeypatch.setattr("admin.ai_models.requests.get", lambda *args, **kwargs: MockResponse())

    response = client.post(f"/admin/ai-models/{model.id}/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "wadhwani_glaucoma"
    assert payload["payload"]["status"] == "healthy"


def test_ai_model_health_rejects_unlinked_model(client, login_user, db_session):
    login_user("test_admin", "Test@2026")

    model = AIModel(name="plain_model", version="1.0", description="plain")
    db_session.add(model)
    db_session.flush()

    response = client.post(f"/admin/ai-models/{model.id}/health")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "not linked" in payload["message"]


def test_madhunetra_configuration_is_on_owning_model_edit_and_survives_metadata_save(
    client,
    login_user,
    db_session,
):
    login_user("test_admin", "Test@2026")
    integration = db_session.query(AIModelIntegration).filter_by(provider="wai_dr_dme").one()
    model = db_session.query(AIModel).filter_by(id=integration.ai_model_id).one()
    diseases = [link.disease for link in model.disease_links if link.active]

    listing = client.get("/admin/ai-models")
    edit = client.get(f"/admin/ai-models/{model.id}/edit")

    assert listing.status_code == 200
    assert b"Save DR + DME API configuration" not in listing.data
    assert edit.status_code == 200
    assert b"MadhuNetrAI DR + DME API" in edit.data
    assert b"Save DR + DME API configuration" in edit.data
    assert b"Link to Wadhwani Glaucoma API" not in edit.data
    assert b"js-madhunetra-toggle" in edit.data
    assert b"madhunetra_api_base_url" in edit.data and b"disabled" in edit.data

    response = client.post(
        f"/admin/ai-models/{model.id}/edit",
        data={
            "name": model.name,
            "version": model.version,
            "description": "updated combined model",
            "disease_ids": [str(disease.id) for disease in diseases],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    db_session.expire_all()
    preserved = db_session.query(AIModelIntegration).filter_by(ai_model_id=model.id).one()
    assert preserved.provider == "wai_dr_dme"
    assert preserved.environment == "staging"
