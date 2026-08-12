from datetime import date
import uuid

from data_authorization.models import ProjectRoleGrant
from models import (
    DirectImageUpload,
    EncounterSetGradingPackage,
    EncounterSetImage,
    GradingTask,
    PatientEncounters,
    Project,
    Role,
    User,
)
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileDisease,
    UploadProfileKind,
)


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def test_project_review_pages_and_api_are_scoped_and_non_pii(app, db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital_a"])
    allowed_lab = db_session.merge(core_test_data["lab_a1"])
    blocked_lab = db_session.merge(core_test_data["lab_a2"])
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = db_session.merge(core_test_data["camera"])
    area = db_session.merge(core_test_data["area"])
    collaborator = _role(db_session, "collaborator")
    user = User(
        username="project_review_only_user",
        password_hash="x",
        is_active=True,
    )
    project = Project(title="Review Project", code="REVIEW_PROJECT", active=True)
    blocked_project = Project(title="Blocked Review Project", code="BLOCKED_REVIEW_PROJECT", active=True)
    db_session.add_all([user, project, blocked_project])
    db_session.flush()
    db_session.add(ProjectRoleGrant(
        project_id=project.id,
        user_id=user.id,
        role_id=collaborator.id,
        scope_type="lab_unit",
        lab_unit_id=allowed_lab.id,
        active=True,
    ))
    profile = UploadProfile(name="Review Direct Intake", active=True)
    hidden_profile = UploadProfile(name="Hidden Disabled Intake", active=False)
    db_session.add_all([profile, hidden_profile])
    db_session.flush()
    mapping = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    hidden_mapping = ProjectUploadProfile(project_id=project.id, upload_profile_id=hidden_profile.id, active=True)
    db_session.add_all([mapping, hidden_mapping])
    db_session.flush()
    db_session.add_all([
        UploadProfileKind(upload_profile_id=profile.id, upload_kind="direct_image"),
        UploadProfileDisease(upload_profile_id=profile.id, disease_id=disease.id, is_default=True),
        ProjectUploadProfileAssignment(
            project_upload_profile_id=mapping.id,
            user_id=user.id,
            lab_unit_id=allowed_lab.id,
            active=True,
        ),
    ])
    allowed_encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="SECRET PATIENT NAME",
        patient_id="SECRET-MRN-100",
        capture_date="2026-08-12",
        capture_date_dt=date(2026, 8, 12),
        lab_unit_id=allowed_lab.id,
        project_id=project.id,
        is_set_based=True,
        encounter_verified_status="verified",
    )
    blocked_encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="BLOCKED PATIENT NAME",
        patient_id="BLOCKED-MRN-100",
        capture_date="2026-08-12",
        capture_date_dt=date(2026, 8, 12),
        lab_unit_id=blocked_lab.id,
        project_id=project.id,
        is_set_based=True,
        encounter_verified_status="pending",
    )
    db_session.add_all([allowed_encounter, blocked_encounter])
    db_session.flush()
    image = EncounterSetImage(
        uuid=str(uuid.uuid4()),
        patient_encounter_id=allowed_encounter.id,
        spatial_position=1,
        original_filename="allowed.jpg",
        folder_rel="files/project_review",
        hospital_id=hospital.id,
        project_id=project.id,
    )
    direct = DirectImageUpload(
        uuid=str(uuid.uuid4()),
        original_filename="direct.jpg",
        filename="direct.jpg",
        folder_rel="files/project_review",
        file_hash=uuid.uuid4().hex,
        uploader_id=user.id,
        hospital_id=hospital.id,
        lab_unit_id=allowed_lab.id,
        project_id=project.id,
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
        is_mydriatic=False,
        is_pregraded=True,
    )
    package = EncounterSetGradingPackage(
        patient_encounter_id=allowed_encounter.id,
        name="Unified Package",
        code="unified_review",
        grading_mode="unified",
        state="pending",
    )
    db_session.add_all([image, direct, package])
    db_session.flush()
    db_session.add_all([
        GradingTask(
            direct_image_upload_id=direct.id,
            disease_id=disease.id,
            lab_unit_id=allowed_lab.id,
            state="final",
            grading_target_level="image",
        ),
        GradingTask(
            patient_encounter_id=allowed_encounter.id,
            encounter_set_package_id=package.id,
            disease_id=disease.id,
            lab_unit_id=allowed_lab.id,
            state="arbitration",
            grading_target_level="encounter",
        ),
    ])
    db_session.commit()

    with app.test_client(user=user) as client:
        index = client.get("/projects/")
        assert index.status_code == 200
        assert b"selectedProjectId" in index.data
        assert str(project.id).encode() in index.data

        summary = client.get(f"/api/projects/{project.id}/review/summary")
        assert summary.status_code == 200
        metrics = {item["key"]: item["value"] for item in summary.get_json()["data"]["metrics"]}
        assert metrics["encounter_sets"] == 1
        assert metrics["single_uploads"] == 1
        assert metrics["total_images"] == 2
        assert metrics["grading_tasks"] == 2
        configuration = summary.get_json()["data"]
        assert [source["name"] for source in configuration["sources"]] == ["Review Direct Intake"]
        assert configuration["grading_targets"][0]["target_type"] == "Single-image disease-wise"
        assert configuration["configured_users"][0]["roles"] == ["collaborator"]
        assert "Hidden Disabled Intake" not in summary.get_data(as_text=True)
        summary_page = client.get(f"/projects/{project.id}/summary")
        assert summary_page.status_code == 200
        assert b"Effective configuration" in summary_page.data
        assert b"SECRET PATIENT NAME" not in summary_page.data

        uploads = client.get(f"/projects/{project.id}/uploads")
        assert uploads.status_code == 200
        html = uploads.get_data(as_text=True)
        assert allowed_encounter.uuid in html
        assert direct.uuid in html
        assert blocked_encounter.uuid not in html
        assert "SECRET PATIENT NAME" not in html
        assert "SECRET-MRN-100" not in html

        gradings = client.get(f"/api/projects/{project.id}/review/gradings")
        grading_rows = gradings.get_json()["data"]["rows"]
        assert {(row["target_type"], row["grading_mode"], row["state"]) for row in grading_rows} == {
            ("Single image", "disease specific", "final"),
            ("EncounterSet", "unified", "arbitration"),
        }
        gradings_page = client.get(f"/projects/{project.id}/gradings")
        assert gradings_page.status_code == 200
        assert b"Pending adjudication" in gradings_page.data
        assert b"SECRET-MRN-100" not in gradings_page.data

        blocked = client.get(f"/api/projects/{blocked_project.id}/review/summary")
        assert blocked.status_code == 404


def test_projects_navbar_is_available_to_project_only_members(app, db_session):
    user = User(username="project_nav_only_user", password_hash="x", is_active=True)
    db_session.add(user)
    db_session.commit()

    with app.test_client(user=user) as client:
        response = client.get("/projects/")

    assert response.status_code == 200
    assert 'href="/projects/"' in response.get_data(as_text=True)
