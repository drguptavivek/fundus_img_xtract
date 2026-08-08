from uuid import uuid4

from bs4 import BeautifulSoup

from grading_allocation.models import ProjectGraderAllocation
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
    db_session.add(
        ProjectGraderAllocation(
            project_id=project.id,
            user_id=resident.id,
            lab_unit_id=lab.id,
            scope="disease_image",
            disease_id=disease.id,
            capacity="resident",
            active=True,
            created_by_user_id=admin.id,
            updated_by_user_id=admin.id,
        )
    )
    db_session.flush()
    _authenticate(client, admin)

    response = client.get(f"/admin/upload-projects/{project.id}/workspace")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Grading Allocation" in body
    assert "Legacy eligibility active" in body
    assert "EncounterSet-scoped encounter schemes" in body
    assert "Image-scoped EncounterSet schemes" in body
    assert "Image-wise non-set schemes" in body
    assert 'data-grading-target-family="image_wise_non_set"' in body
    assert f"{disease.name} / Non-EncounterSet Images" in body
    assert "Allocation is not ready for enforcement" not in body
    assert "Arbitrator allocation is optional and independent" in body
    assert resident.username in body
    assert (
        f'/api/projects/{project.id}/grader-allocation-candidates'
        in body
    )
    assert arbitrator.username in body
    assert f'/api/projects/{project.id}/grader-allocations' in body
    assert f'/api/projects/{project.id}/grader-allocation-policy' in body
    soup = BeautifulSoup(body, "html.parser")
    policy_form = soup.find("form", attrs={"data-grading-allocation-form": "policy"})
    assert policy_form is not None
    enable_button = policy_form.find("button", string=lambda text: text and "Enable" in text)
    assert enable_button is not None
    assert not enable_button.has_attr("disabled")
