from uuid import uuid4

from grading_allocation.dtos import (
    EncounterSetQueueSlotDTO,
    ProjectEncounterSetQueueDTO,
)
from models import Project
from project_configuration.models import ProjectLabUnit
from tests.helpers.factories import UserFactory
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileDisease,
)


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
            ProjectLabUnit(project_id=project.id, lab_unit_id=lab.id, active=True),
            ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True),
            UploadProfileDisease(upload_profile_id=profile.id, disease_id=disease.id, is_default=True),
        ]
    )
    admin = UserFactory.create_admin(db_session, username=f"api_allocation_admin_{suffix}")
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"api_allocation_resident_{suffix}",
        lab_units=[],
    )
    field_ophthalmologist = UserFactory.create_by_role(
        db_session,
        "field_ophthalmologist",
        username=f"api_allocation_field_oph_{suffix}",
        lab_units=[],
    )
    field_optometrist = UserFactory.create_by_role(
        db_session,
        "field_optometrist",
        username=f"api_allocation_field_opt_{suffix}",
        lab_units=[],
    )
    nonclinical = UserFactory.create_by_role(
        db_session,
        "data_manager",
        username=f"api_allocation_nonclinical_{suffix}",
        lab_units=[],
    )
    db_session.flush()
    _authenticate(client, admin)

    get_response = client.get(f"/api/projects/{project.id}/grader-allocations")
    assert get_response.status_code == 200
    assert "policy" not in get_response.get_json()
    target = get_response.get_json()["targets"][0]
    assert target["scope"] == "disease_image"
    assert target["task_family"] == "image_wise_non_set"
    assert target["diseases"] == [{"id": disease.id, "name": disease.name}]

    candidates_response = client.get(
        f"/api/projects/{project.id}/grader-allocation-candidates",
        query_string={"lab_unit_id": lab.id, "capacity": "resident"},
    )
    assert candidates_response.status_code == 200
    candidate = next(
        row
        for row in candidates_response.get_json()["candidates"]
        if row["id"] == resident.id
    )
    assert candidate["is_member_of_lab"] is False
    candidate_ids = {row["id"] for row in candidates_response.get_json()["candidates"]}
    assert field_ophthalmologist.id in candidate_ids
    assert field_optometrist.id not in candidate_ids
    assert nonclinical.id not in candidate_ids

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


def test_arbitrator_candidates_include_active_ophthalmologists_outside_target_lab(
    client,
    db_session,
    core_test_data,
):
    suffix = uuid4().hex[:8]
    project = Project(
        title=f"Cross Lab Candidates {suffix}",
        code=f"CROSS-LAB-{suffix}",
        active=True,
    )
    db_session.add(project)
    admin = UserFactory.create_admin(
        db_session,
        username=f"cross_lab_admin_{suffix}",
    )
    ophthalmologist = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"cross_lab_ophthalmologist_{suffix}",
        lab_units=[],
    )
    db_session.add(
        ProjectLabUnit(
            project_id=project.id,
            lab_unit_id=core_test_data["lab_unit"].id,
            active=True,
        )
    )
    db_session.flush()
    _authenticate(client, admin)

    response = client.get(
        f"/api/projects/{project.id}/grader-allocation-candidates",
        query_string={
            "lab_unit_id": core_test_data["lab_unit"].id,
            "capacity": "arbitrator",
        },
    )

    assert response.status_code == 200
    candidates = response.get_json()["candidates"]
    assert any(row["id"] == ophthalmologist.id for row in candidates)


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


def test_grader_allocation_policy_endpoint_is_removed(client, db_session):
    project = Project(
        title=f"No Toggle Project {uuid4().hex[:8]}",
        code=f"NO-TOGGLE-{uuid4().hex[:8]}",
        active=True,
    )
    db_session.add(project)
    db_session.flush()

    response = client.put(
        f"/api/projects/{project.id}/grader-allocation-policy",
        json={"enforcement_enabled": False},
    )

    assert response.status_code == 404


def test_project_encounter_set_queue_api_returns_current_users_queues(
    client,
    db_session,
    monkeypatch,
):
    grader = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"project_queue_api_{uuid4().hex[:8]}",
        lab_units=[],
    )
    db_session.flush()
    _authenticate(client, grader)
    queue = ProjectEncounterSetQueueDTO(
        project_id=3,
        project_title="Integrated DR Glaucoma Screening",
        project_code="ICMR-VG",
        target_key="disease_encounter:1:15",
        target_label="Glaucoma / EncounterSet",
        encounter_set_type_name="Remidio API Standard Encounter Set",
        slots=(
            EncounterSetQueueSlotDTO(
                slot="resident",
                package_count=1,
                task_count=1,
                first_package_uuid="package-uuid",
            ),
        ),
    )
    observed = {}

    # The route now goes through the live accessor in grading.queue_cards,
    # which returns already-serialised dicts rather than DTOs.
    def _queues(_db, *, user_id, refresh=False):
        observed["user_id"] = user_id
        observed["refresh"] = refresh
        return [queue.to_dict()]

    monkeypatch.setattr(
        "api.grading_allocations.project_encounter_set_cards",
        _queues,
    )

    response = client.get("/api/grading/project-encounter-set-queues")

    assert response.status_code == 200
    assert observed["user_id"] == grader.id
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["queues"][0]["project"]["code"] == "ICMR-VG"
    assert payload["queues"][0]["slots"] == [
        {
            "slot": "resident",
            "label": "Resident",
            "package_count": 1,
            "task_count": 1,
            "first_package_uuid": "package-uuid",
        }
    ]
