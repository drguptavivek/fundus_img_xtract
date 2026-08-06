from uuid import uuid4

from models import Project
from tests.helpers.factories import UserFactory
from upload_profiles.models import ProjectUploadProfile, UploadProfile, UploadProfileDisease


def _authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_grader_allocation_api_crud(client, db_session, core_test_data):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    suffix = uuid4().hex[:8]
    project = Project(title=f"API Allocation {suffix}", code=f"API-ALLOC-{suffix}", active=True)
    profile = UploadProfile(name=f"API Allocation Profile {suffix}", active=True)
    db_session.add_all([project, profile])
    db_session.flush()
    db_session.add_all(
        [
            ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True),
            UploadProfileDisease(upload_profile_id=profile.id, disease_id=disease.id, is_default=True),
        ]
    )
    admin = UserFactory.create_admin(db_session, username=f"api_allocation_admin_{suffix}")
    resident = UserFactory.create_by_role(
        db_session,
        "resident",
        username=f"api_allocation_resident_{suffix}",
        lab_units=[lab],
    )
    db_session.flush()
    _authenticate(client, admin)

    get_response = client.get(f"/api/projects/{project.id}/grader-allocations")
    assert get_response.status_code == 200
    target = get_response.get_json()["targets"][0]
    assert target["scope"] == "disease_image"
    assert target["task_family"] == "image_wise_non_set"
    assert target["diseases"] == [{"id": disease.id, "name": disease.name}]

    create_response = client.post(
        f"/api/projects/{project.id}/grader-allocations",
        json={
            "user_id": resident.id,
            "lab_unit_id": lab.id,
            "scope": "disease_image",
            "disease_id": disease.id,
            "capacity": "resident",
        },
    )
    assert create_response.status_code == 201
    allocation = create_response.get_json()["allocation"]
    assert allocation["capacity"] == "resident"
    assert allocation["active"] is True

    delete_response = client.delete(
        f"/api/projects/{project.id}/grader-allocations/{allocation['id']}"
    )
    assert delete_response.status_code == 200
    assert delete_response.get_json()["allocation"]["active"] is False


def test_grader_allocation_api_rejects_invalid_target_shape(
    client,
    db_session,
    core_test_data,
):
    suffix = uuid4().hex[:8]
    project = Project(title=f"Invalid Allocation {suffix}", code=f"INV-ALLOC-{suffix}", active=True)
    db_session.add(project)
    admin = UserFactory.create_admin(db_session, username=f"invalid_allocation_admin_{suffix}")
    db_session.flush()
    _authenticate(client, admin)

    response = client.post(
        f"/api/projects/{project.id}/grader-allocations",
        json={
            "user_id": admin.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "scope": "encounter_set_unified",
            "disease_id": core_test_data["dr"].id,
            "capacity": "arbitrator",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "grading_allocation_error"
