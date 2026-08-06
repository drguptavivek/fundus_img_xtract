from uuid import uuid4

from models import Project
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


def test_project_workspace_renders_grader_allocation_editor(
    client,
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    suffix = uuid4().hex[:8]
    project = Project(
        title=f"Allocation UI {suffix}",
        code=f"ALLOC-UI-{suffix}",
        active=True,
    )
    profile = UploadProfile(name=f"Allocation UI Profile {suffix}", active=True)
    db_session.add_all([project, profile])
    db_session.flush()
    db_session.add_all(
        [
            ProjectUploadProfile(
                project_id=project.id,
                upload_profile_id=profile.id,
                active=True,
            ),
            UploadProfileDisease(
                upload_profile_id=profile.id,
                disease_id=disease.id,
                is_default=True,
            ),
        ]
    )
    admin = UserFactory.create_admin(
        db_session,
        username=f"allocation_ui_admin_{suffix}",
    )
    admin.lab_units.append(lab)
    resident = UserFactory.create_by_role(
        db_session,
        "resident",
        username=f"allocation_ui_resident_{suffix}",
        lab_units=[lab],
    )
    arbitrator = UserFactory.create_ophthalmologist(
        db_session,
        username=f"allocation_ui_arbitrator_{suffix}",
        lab_units=[lab],
    )
    db_session.flush()
    _authenticate(client, admin)

    response = client.get(f"/admin/upload-projects/{project.id}/workspace")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Grading Allocation" in body
    assert "Legacy eligibility active" in body
    assert f"{disease.name} / Images" in body
    assert "Allocation is not ready for enforcement" in body
    assert resident.username in body
    assert 'data-capacities="resident"' in body
    assert arbitrator.username in body
    assert 'data-capacities="resident arbitrator"' in body
    assert f'/api/projects/{project.id}/grader-allocations' in body
    assert f'/api/projects/{project.id}/grader-allocation-policy' in body
