from datetime import date

from data_authorization.models import ProjectRoleGrant
from models import (
    DiseaseGrading,
    EncounterSetImage,
    Grade,
    GradingTask,
    Job,
    PatientEncounters,
    Project,
    Role,
    User,
)
from project_configuration.models import ProjectLabUnit
from project_review.export_service import run_project_export_job


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def test_data_manager_project_export_page_preview_and_queue(
    app, db_session, core_test_data, monkeypatch, tmp_path
):
    lab = db_session.merge(core_test_data["lab_a1"])
    disease = db_session.merge(core_test_data["glaucoma"])
    label = db_session.query(DiseaseGrading).filter_by(disease_id=disease.id).first()
    user = User(username="project_export_manager", password_hash="x", is_active=True)
    project = Project(title="Export Project", code="EXPORT_PROJECT", active=True)
    db_session.add_all([user, project])
    db_session.flush()
    db_session.add_all([
        ProjectLabUnit(project_id=project.id, lab_unit_id=lab.id, active=True),
        ProjectRoleGrant(
            project_id=project.id, user_id=user.id, role_id=_role(db_session, "data_manager").id,
            scope_type="project", lab_unit_id=None, active=True,
        ),
    ])
    encounter = PatientEncounters(
        name="SHOULD NOT EXPORT", patient_id="SECRET-MRN", capture_date="2026-09-01",
        capture_date_dt=date(2026, 9, 1), lab_unit_id=lab.id, project_id=project.id,
        is_set_based=True,
        metadata_json={"patient": {"sex": "female"}, "encounter": {"mode_capture": "clinic"}},
    )
    db_session.add(encounter)
    db_session.flush()
    image = EncounterSetImage(
        patient_encounter_id=encounter.id, spatial_position=1,
        original_filename="SECRET-MRN.jpg", folder_rel="files/test",
    )
    db_session.add(image)
    db_session.flush()
    task = GradingTask(
        encounter_set_image_id=image.id, disease_id=disease.id, lab_unit_id=lab.id,
        grading_target_level="image", state="resident_done",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(Grade(
        task_id=task.id, grader_user_id=user.id, role_slot="resident",
        disease_grading_id=label.id, grade_name=label.impression,
    ))
    db_session.commit()

    queued = []
    monkeypatch.setattr(
        "api.project_review.enqueue_project_export",
        lambda _app, token, payload: queued.append((token, payload)),
    )
    with app.test_client(user=user) as client:
        summary = client.get(f"/projects/{project.id}/summary")
        assert summary.status_code == 200
        assert b"Project Export" in summary.data
        page = client.get(f"/projects/{project.id}/export")
        assert page.status_code == 200
        assert b"Project Export" in page.data
        assert b"SECRET-MRN" not in page.data

        preview = client.get(
            f"/api/projects/{project.id}/exports/preview?grading_filter=any_graded"
        )
        assert preview.status_code == 200
        assert preview.get_json()["data"] == {
            "encounter_count": 1,
            "image_count": 1,
            "task_count": 1,
            "image_export_limit": 250,
            "image_export_allowed": True,
        }

        response = client.post(
            f"/api/projects/{project.id}/exports",
            json={"kind": "workbook", "grading_filter": "any_graded"},
        )
        assert response.status_code == 202
        token = response.get_json()["data"]["job_token"]
        job = db_session.query(Job).filter_by(token=token).one()
        assert job.project_id == project.id
        assert job.upload_type == "project_export"
        assert queued[0][1]["actor_user_id"] == user.id

        monkeypatch.setattr("project_review.export_service.EXPORT_DIR", tmp_path)
        monkeypatch.setattr("api.project_review.EXPORT_DIR", tmp_path)
        monkeypatch.setattr("jobs.routes.EXPORT_DIR", tmp_path)
        run_project_export_job(token, queued[0][1])
        workbook = tmp_path / token / "project_encounterset_export.xlsx"
        assert workbook.exists()
        assert b"SECRET-MRN" not in workbook.read_bytes()

        status_page = client.get(f"/jobs/{token}/view")
        assert status_page.status_code == 200
        status = client.get(f"/jobs/{token}").get_json()
        assert status["status"] == "done"
        assert status["export_files"] == ["project_encounterset_export.xlsx"]
        download = client.get(
            f"/api/projects/{project.id}/exports/{token}/project_encounterset_export.xlsx"
        )
        assert download.status_code == 200
        assert download.headers["Content-Disposition"].startswith("attachment;")
        recent = client.get(f"/api/projects/{project.id}/exports/recent")
        assert recent.status_code == 200
        recent_data = recent.get_json()["data"]
        assert len(recent_data) == 1
        assert recent_data[0]["job_token"] == token
        assert recent_data[0]["status"] == "done"
        assert recent_data[0]["files"][0]["filename"] == "project_encounterset_export.xlsx"


def test_project_image_export_rejects_more_than_250_matches(
    app, db_session, core_test_data, monkeypatch
):
    lab = db_session.merge(core_test_data["lab_a1"])
    user = User(username="project_export_limit_manager", password_hash="x", is_active=True)
    project = Project(title="Limit Project", code="LIMIT_PROJECT", active=True)
    db_session.add_all([user, project])
    db_session.flush()
    db_session.add_all([
        ProjectLabUnit(project_id=project.id, lab_unit_id=lab.id, active=True),
        ProjectRoleGrant(
            project_id=project.id, user_id=user.id, role_id=_role(db_session, "data_manager").id,
            scope_type="project", lab_unit_id=None, active=True,
        ),
    ])
    db_session.commit()
    monkeypatch.setattr(
        "api.project_review.project_export_preview",
        lambda *_args, **_kwargs: {
            "encounter_count": 251, "image_count": 999, "task_count": 999,
            "image_export_limit": 250, "image_export_allowed": False,
        },
    )
    with app.test_client(user=user) as client:
        response = client.post(
            f"/api/projects/{project.id}/exports",
            json={"kind": "images", "grading_filter": "all"},
        )
    assert response.status_code == 400
    assert "limited to 250" in response.get_json()["error"]
