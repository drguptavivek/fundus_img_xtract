from uuid import uuid4

from encounter_set_types.models import EncounterSetType
from models import Hospital, LabUnit, Project
from tests.conftest import create_authenticated_client
from tests.helpers.factories import UserFactory
from upload_profiles.models import ProjectUploadProfile, UploadProfile, UploadProfileEncounterSetType


def test_legacy_iitk_pages_redirect_to_project_admin(app, db_session, core_test_data):
    admin_user = UserFactory.create_admin(db_session, username=f"iitk_admin_{uuid4().hex[:8]}")
    client = create_authenticated_client(app, admin_user, db_session)

    page = client.get("/admin/iitk")
    partial = client.get("/admin/iitk/workspace")
    mappings = client.get("/api/iitk/site-mappings")

    assert page.status_code == 302
    assert partial.status_code == 302
    assert page.headers["Location"].endswith("/admin/upload-projects")
    assert partial.headers["Location"].endswith("/admin/upload-projects")
    assert mappings.status_code == 200
    assert {row["site"] for row in mappings.get_json()["data"]} == {"delhi", "kalyani", "bilaspur", "nagpur"}


def test_project_admin_owns_iitk_flag_and_token(app, db_session, core_test_data):
    hospital = db_session.query(Hospital).filter_by(name="RPC AIIMS").one_or_none()
    if hospital is None:
        hospital = Hospital(name="RPC AIIMS")
        db_session.add(hospital)
        db_session.flush()
    lab_unit = db_session.query(LabUnit).filter_by(hospital_id=hospital.id, name="Deepsekhar Das").one_or_none()
    if lab_unit is None:
        lab_unit = LabUnit(hospital_id=hospital.id, name="Deepsekhar Das")
        db_session.add(lab_unit)
        db_session.flush()
    admin_user = UserFactory.create_admin(db_session, username=f"iitk_project_admin_{uuid4().hex[:8]}")
    admin_user.lab_units.append(lab_unit)
    project = Project(title=f"IITK Project {uuid4()}", code=f"IITK{uuid4().hex[:8]}", active=True)
    profile = UploadProfile(name=f"IITK Profile {uuid4()}", active=True)
    encounter_type = EncounterSetType(
        name=f"IITK Type {uuid4()}", code=f"iitk_{uuid4().hex[:8]}", active=True,
        metadata_schema_json={"fields": []}, asset_rules_json={},
    )
    db_session.add_all([project, profile, encounter_type])
    db_session.flush()
    mapping = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    db_session.add(mapping)
    db_session.flush()
    db_session.add(UploadProfileEncounterSetType(
        upload_profile_id=profile.id, encounter_set_type_id=encounter_type.id, active=True,
    ))
    db_session.flush()
    client = create_authenticated_client(app, admin_user, db_session)

    workspace = client.get(f"/admin/upload-projects/{project.id}/workspace")
    saved = client.post(
        f"/api/iitk/projects/{project.id}/configuration",
        data={"active": "true", "api_token": "private-token"},
    )
    refreshed = client.get(f"/api/iitk/projects/{project.id}/configuration")

    assert workspace.status_code == 200
    assert b"IITK API populated project" in workspace.data
    assert b"IITK API token" in workspace.data
    assert b"Project upload profile" not in workspace.data
    assert saved.status_code == 200
    assert saved.get_json()["data"]["iitk_project_config"]["token_configured"] is True
    assert refreshed.status_code == 200
    assert refreshed.get_json()["data"]["iitk_project_config"]["active"] is True
