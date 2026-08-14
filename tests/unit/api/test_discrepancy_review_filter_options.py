from review.discrepancy_scope import (
    DiseaseFilterOption,
    DiscrepancyFilterOptions,
    DiscrepancyScopeError,
    LabUnitFilterOption,
    ProjectFilterOption,
)
from tests.helpers.factories import UserFactory


def _authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_filter_options_api_returns_project_scoped_dependencies(
    client, db_session, monkeypatch
):
    admin = UserFactory.create_admin(db_session, username="filter-options-admin")
    _authenticate(client, admin)
    captured = {}
    monkeypatch.setattr(
        "api.discrepancy_review.discrepancy_lab_unit_ids",
        lambda db, user: {4},
    )

    def fake_options(db, *, user, allowed_lab_unit_ids, project_id):
        captured.update(
            user_id=user.id,
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            project_id=project_id,
        )
        return DiscrepancyFilterOptions(
            projects=(ProjectFilterOption(7, "Study", True),),
            diseases=(DiseaseFilterOption(2, "Glaucoma"),),
            lab_units=(LabUnitFilterOption(4, "Retina", 3, "Hospital"),),
            project_id=project_id,
        )

    monkeypatch.setattr(
        "api.discrepancy_review.list_discrepancy_filter_options",
        fake_options,
    )

    response = client.get("/api/review/filter-options?project_id=7")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["diseases"] == [{"id": 2, "name": "Glaucoma"}]
    assert payload["data"]["lab_units"][0]["label"] == "Hospital - Retina"
    assert captured == {
        "user_id": admin.id,
        "allowed_lab_unit_ids": {4},
        "project_id": 7,
    }


def test_discrepancy_review_page_renders_project_filter(
    client, db_session, monkeypatch
):
    admin = UserFactory.create_admin(db_session, username="project-filter-page-admin")
    _authenticate(client, admin)
    monkeypatch.setattr(
        "review.route_discrepancy_review.list_discrepancy_filter_options",
        lambda db, user, allowed_lab_unit_ids, project_id: DiscrepancyFilterOptions(
            projects=(ProjectFilterOption(7, "Study", True),),
            diseases=(),
            lab_units=(),
            project_id=project_id,
        ),
    )

    response = client.get("/review/discrepancy-review", follow_redirects=True)

    assert response.status_code == 200
    assert b'id="projectSelect"' in response.data
    assert b"Study" in response.data


def test_filter_options_api_hides_unavailable_project(
    client, db_session, monkeypatch
):
    admin = UserFactory.create_admin(db_session, username="unavailable-project-admin")
    _authenticate(client, admin)
    monkeypatch.setattr(
        "api.discrepancy_review.discrepancy_lab_unit_ids",
        lambda db, user: {4},
    )

    def unavailable(*args, **kwargs):
        raise DiscrepancyScopeError("Project is unavailable for discrepancy review.")

    monkeypatch.setattr(
        "api.discrepancy_review.list_discrepancy_filter_options",
        unavailable,
    )

    response = client.get("/api/review/filter-options?project_id=999")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": "Project is unavailable for discrepancy review.",
    }
