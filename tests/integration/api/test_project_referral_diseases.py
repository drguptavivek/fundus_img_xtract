from models import Disease, Project, ProjectReferralDisease


def test_project_referral_disease_api_adds_referral_only_option(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project = Project(title="Referral API Project", code="REFERRAL_API", active=True)
    amd = Disease(name="Referral API AMD", remidio_ocr_linkage="amd")
    db_session.add_all([project, amd])
    db_session.flush()

    with app.test_client(user=test_users["admin"]) as client:
        updated = client.put(
            f"/api/projects/{project.id}/referral-diseases",
            json={"disease_ids": [amd.id]},
        )
        loaded = client.get(f"/api/projects/{project.id}/referral-diseases")

    assert updated.status_code == 200
    assert loaded.status_code == 200
    assert loaded.get_json()["data"]["configured_disease_ids"] == [amd.id]
    assert {row["name"] for row in loaded.get_json()["data"]["effective_diseases"]} == {"Referral API AMD"}
    assert db_session.query(ProjectReferralDisease).filter_by(
        project_id=project.id,
        disease_id=amd.id,
        active=True,
    ).one()


def test_project_referral_disease_api_deactivates_removed_option(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project = Project(title="Referral Removal Project", code="REFERRAL_REMOVE", active=True)
    amd = Disease(name="Referral Removal AMD", remidio_ocr_linkage="amd")
    configured = ProjectReferralDisease(project=project, disease=amd, active=True)
    db_session.add(configured)
    db_session.flush()

    with app.test_client(user=test_users["admin"]) as client:
        response = client.put(
            f"/api/projects/{project.id}/referral-diseases",
            json={"disease_ids": []},
        )

    assert response.status_code == 200
    db_session.refresh(configured)
    assert configured.active is False
