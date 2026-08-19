from __future__ import annotations

import json
from datetime import date
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from uuid import uuid4

from encounter_sets.models import EncounterSetAttachment
from auth.utils import utcnow
from models import AIInferenceRun, AIModel, EncounterSetImage, GradingTask, Job, JobItem, PatientEncounters, Project
from remidio_api_uploads.wadhwani_inference import (
    ENCOUNTER_SETS_PER_PAGE,
    MAX_ENCOUNTER_SETS_PER_BATCH,
    InferenceFilters,
    _glaucoma_ocr_summary,
    _image_matches_filters,
    _job_workflow,
    _wadhwani_status_by_image,
)
from remote_inference.dr_dme import CandidatePage, MAX_MANUAL_ENCOUNTERS


def test_wadhwani_status_uses_only_the_glaucoma_task(db_session, core_test_data):
    lab_unit = core_test_data["lab_unit"]
    glaucoma = core_test_data["glaucoma"]
    dr = core_test_data["dr"]
    encounter = PatientEncounters(
        name=f"Wadhwani status {uuid4()}",
        patient_id=f"patient-{uuid4()}",
        capture_date="2026-08-12",
        capture_date_dt=date(2026, 8, 12),
        is_set_based=True,
        lab_unit_id=lab_unit.id,
    )
    image = EncounterSetImage(
        patient_encounter=encounter,
        spatial_position=1,
        original_filename=f"{uuid4()}.png",
        folder_rel="wadhwani-page-tests",
        hospital_id=lab_unit.hospital_id,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        is_not_gradable=False,
    )
    dr_task = GradingTask(
        encounter_set_image=image,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
        state="pending",
        grading_target_level="image",
    )
    glaucoma_task = GradingTask(
        encounter_set_image=image,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        state="pending",
        grading_target_level="image",
    )
    model = AIModel(name=f"Wadhwani page {uuid4()}", version="test")
    db_session.add_all([encounter, image, dr_task, glaucoma_task, model])
    db_session.flush()
    run = AIInferenceRun(
        task_id=glaucoma_task.id,
        ai_model_id=model.id,
        source="internal",
        status="success",
    )
    db_session.add(run)
    db_session.flush()

    status = _wadhwani_status_by_image(
        db_session,
        [image],
        model.id,
        glaucoma.id,
    )[image.id]

    assert status["has_prior"] is True
    assert status["task_id"] == glaucoma_task.id
    assert status["run_id"] == run.id
    assert status["run_status"] == "success"


def test_glaucoma_ocr_presence_does_not_depend_on_screening_result():
    negative = EncounterSetAttachment(
        patient_encounter_id=1,
        asset_kind="pdf",
        original_filename="negative.pdf",
        metadata_json={
            "ocr": {
                "glaucoma_report": {
                    "glaucoma_data": {"result": "No referable glaucoma."}
                }
            }
        },
    )
    positive = EncounterSetAttachment(
        patient_encounter_id=2,
        asset_kind="pdf",
        original_filename="positive.pdf",
        metadata_json={
            "ocr": {
                "glaucoma_report": {
                    "glaucoma_data": {"result": "Referable glaucoma."}
                }
            }
        },
    )
    unrelated = EncounterSetAttachment(
        patient_encounter_id=3,
        asset_kind="pdf",
        original_filename="dr.pdf",
        metadata_json={"ocr": {"dr_report": {"result": "referable"}}},
    )

    assert _glaucoma_ocr_summary([negative])["result"] == "No referable glaucoma."
    assert _glaucoma_ocr_summary([positive])["result"] == "Referable glaucoma."
    assert _glaucoma_ocr_summary([unrelated]) is None


def test_existing_image_filters_remain_conjunctive():
    filters = InferenceFilters(
        project_id=3,
        capture_date_from="",
        capture_date_to="",
        camera_id="7",
        laterality="od",
        focus="disc",
        glaucoma_report="present",
        include_prior=False,
        page=1,
    )
    image = SimpleNamespace(
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        is_not_gradable=False,
        camera_id=7,
        metadata_json={"laterality": "OD", "focus": "Disc"},
    )

    assert _image_matches_filters(image, filters) is True
    image.camera_id = 8
    assert _image_matches_filters(image, filters) is False
    image.camera_id = 7
    image.metadata_json["focus"] = "macula"
    assert _image_matches_filters(image, filters) is False


def test_encounter_set_page_and_batch_limits_are_25():
    assert ENCOUNTER_SETS_PER_PAGE == 25
    assert MAX_ENCOUNTER_SETS_PER_BATCH == 25
    assert MAX_MANUAL_ENCOUNTERS == 100


def test_dr_dme_workflow_renders_encounter_candidates(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr("remidio_api_uploads.wadhwani_inference.get_db_session", fake_session)
    monkeypatch.setattr(
        "remidio_api_uploads.wadhwani_inference.encounter_service.list_manual_projects",
        lambda db, user: [{"id": 7, "title": "Vision Centre", "code": "VC"}],
    )
    monkeypatch.setattr(
        "remidio_api_uploads.wadhwani_inference.encounter_service.integration_context",
        lambda db: {"is_enabled": True},
    )
    monkeypatch.setattr("remidio_api_uploads.wadhwani_inference._cameras", lambda db: [{"id": 3, "name": "Remidio"}])
    monkeypatch.setattr(
        "remidio_api_uploads.wadhwani_inference.list_dr_dme_candidates",
        lambda db, **kwargs: CandidatePage(rows=({
            "encounter_id": 17,
            "encounter_uuid": "encounter-ui-test",
            "patient_id": "patient-ui-test",
            "patient_age": 61,
            "patient_sex": "female",
            "is_monocular": False,
            "capture_date": "2026-08-18",
            "lab_unit_name": "Vision Lab",
            "eligible": True,
            "eligibility_issues": [],
            "eye_counts": {"right": 2, "left": 3},
            "images": [{
                "id": 71, "uuid": "11111111-1111-1111-1111-111111111111",
                "position": 1, "eye": "right", "camera_name": "Remidio",
            }, {
                "id": 72, "uuid": "22222222-2222-2222-2222-222222222222",
                "position": 2, "eye": "left", "camera_name": "Remidio",
            }],
            "dr_report": {"status": "completed", "result": "Mild DR", "attachment_filename": "dr.pdf"},
            "run_status": "not_requested",
            "report_id": None,
        },), encounter_count=1, image_count=5, page=1, page_size=50, has_prev=False, has_next=False),
    )

    page = client.get("/uploads/encountersets/wadhwani_inference?workflow=dr_dme")
    workspace = client.get("/uploads/encountersets/wadhwani_inference/workspace?workflow=dr_dme&project_id=7&page_size=50&dr_report=present")

    assert page.status_code == 200
    assert b"Encounter DR-DME Screening" in page.data
    assert b"Glaucoma" in page.data and b"DR + DME" in page.data
    assert b'name="eligibility"' in page.data
    assert b'<option value="eligible" selected>Eligible</option>' in page.data
    assert b'Non-monocular: one eye only' in page.data
    assert workspace.status_code == 200
    assert b"encounter-ui-test" in workspace.data
    assert b"OD macula" in workspace.data and b">2</span>" in workspace.data
    assert b"Age 61" in workspace.data and b"Sex Female" in workspace.data
    assert b"Monocular No" in workspace.data
    assert b'aria-label="OD macula images"' in workspace.data
    assert b'aria-label="OS macula images"' in workspace.data
    assert b"Mild DR" in workspace.data and b"Remidio" in workspace.data
    assert b"50 EncounterSets per page" in workspace.data
    assert b'name="selected_encounter_ids"' in workspace.data
    assert b"Select all visible" in workspace.data
    assert (
        b'/uploads/encountersets/browse?project_id=7&amp;month=2026-08&amp;date=2026-08-18&amp;encounter_id=17'
        in workspace.data
    )
    assert b'target="_blank" rel="noopener noreferrer"' in workspace.data
    assert b">View</a>" in workspace.data
    assert b'aria-label="Queue EncounterSet encounter-ui-test"' in workspace.data
    assert b"Queue this EncounterSet</label>" not in workspace.data


def test_both_inference_workspaces_link_encounters_and_support_select_all_visible():
    project_root = Path(__file__).resolve().parents[3]
    glaucoma = (
        project_root / "templates/remidio_api_uploads/_wadhwani_inference_workspace.html"
    ).read_text(encoding="utf-8")
    dr_dme = (
        project_root / "templates/remidio_api_uploads/_madhunetra_workspace.html"
    ).read_text(encoding="utf-8")
    dr_dme_script = (
        project_root / "static/js/madhunetra-inference.js"
    ).read_text(encoding="utf-8")
    dr_dme_page = (
        project_root / "templates/remidio_api_uploads/madhunetra_inference.html"
    ).read_text(encoding="utf-8")

    for template in (glaucoma, dr_dme):
        assert "encounter_set_browser" in template
        assert "month=encounter_date[:7]" in template
        assert "date=encounter_date[:10]" in template
        assert 'target="_blank" rel="noopener noreferrer"' in template
        assert ">View</a>" in template
        assert "Select all visible" in template
    assert 'input[name="selected_encounter_ids"]:not(:disabled)' in dr_dme_script
    assert "encounter-dr-dme-eye-grid" in dr_dme
    assert "grid-template-columns: repeat(auto-fill, 150px)" in dr_dme_page
    assert "htmx:beforeRequest" in dr_dme_script
    assert "syncUrl(source?.id === 'madhunetraWorkspace')" in dr_dme_script


def test_dr_dme_job_status_renders_report_lineage(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr("remidio_api_uploads.wadhwani_inference.get_db_session", fake_session)
    monkeypatch.setattr(
        "remidio_api_uploads.wadhwani_inference.encounter_service.load_job_payload",
        lambda db, token: {
            "token": token,
            "status": "done",
            "error": None,
            "updated_at": utcnow(),
            "done": True,
            "summary": {
                "queued": 0, "processing": 0, "ok": 1, "error": 0,
                "positive_encounters": 1, "positive_images": 1,
            },
            "items": [{
                "encounter_id": 17, "encounter_uuid": "encounter-ui-test",
                "patient_id": "patient-ui-test", "capture_date": "2026-08-18",
                "state": "ok", "message": "Screening complete", "error_code": None,
                "request_id": "request-17", "report_id": "report-17", "reused": False,
                "screening_status": "success",
                "outputs": [{
                    "eye": "right", "is_primary": True, "quality_state": "gradable",
                    "dr_grade": "Mild DR", "dme_grade": "No DME",
                }],
            }],
        },
    )

    response = client.get("/uploads/encountersets/wadhwani_inference/jobs/token-17/status?workflow=dr_dme")

    assert response.status_code == 286
    assert b"encounter-ui-test" in response.data
    assert b"request-17" in response.data and b"report-17" in response.data
    assert b"Screening status" in response.data and b"success" in response.data
    assert b"DR: Mild DR" in response.data and b"DME: No DME" in response.data
    assert b"OD" in response.data and b"Primary" in response.data
    assert b"Positive encounters" in response.data and b"Positive images" in response.data


def test_dr_dme_positive_output_classification():
    from remote_inference.encounter_service import _is_positive_output

    assert _is_positive_output("dr", "Mild DR") is True
    assert _is_positive_output("dme", "DME Present") is True
    assert _is_positive_output("dme", "M1 Referable Diabetic Maculopathy") is True
    assert _is_positive_output("dr", "No DR") is False
    assert _is_positive_output("dme", "No DME") is False
    assert _is_positive_output("dme", "M0 No DME") is False
    assert _is_positive_output("dr", "Not Gradable") is False


def test_dr_dme_job_page_recovers_workflow_from_job_token(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")

    class ScalarResult:
        def scalar_one_or_none(self):
            return "encounter_set_madhunetra_dr_dme"

    @contextmanager
    def fake_session():
        yield SimpleNamespace(execute=lambda _statement: ScalarResult())

    monkeypatch.setattr("remidio_api_uploads.wadhwani_inference.get_db_session", fake_session)

    response = client.get("/uploads/encountersets/wadhwani_inference/jobs/direct-dr-dme-token")

    assert response.status_code == 200
    assert b"Encounter DR-DME Screening Status" in response.data
    assert b"/status?workflow=dr_dme" in response.data


def test_job_workflow_prefers_explicit_dr_dme_without_database_lookup():
    db = SimpleNamespace(execute=lambda _statement: (_ for _ in ()).throw(AssertionError("unexpected query")))

    assert _job_workflow(db, "token", "dr_dme") == "dr_dme"


def test_recent_jobs_button_has_only_the_project_aware_javascript_loader():
    project_root = Path(__file__).resolve().parents[3]
    template = (
        project_root / "templates/remidio_api_uploads/wadhwani_inference.html"
    ).read_text(encoding="utf-8")
    button = template.split('data-recent-wadhwani-jobs', 1)[1].split("</button>", 1)[0]
    script = (
        project_root / "static/js/encounter-set-wadhwani-inference.js"
    ).read_text(encoding="utf-8")

    assert "hx-get=" not in button
    assert "refreshRecentJobs(projectSelect ? projectSelect.value : '')" in script
    assert "if (filterForm())" in script
    assert "htmx:beforeRequest" in script
    assert "syncUrl(source?.id === 'wadhwaniEncounterSetWorkspace')" in script


def test_encounter_set_job_status_shows_positive_inference_count(
    client,
    login_user,
    db_session,
    core_test_data,
):
    lab_unit = core_test_data["lab_unit"]
    encounter = PatientEncounters(
        name=f"Positive WAI {uuid4()}",
        patient_id=f"patient-{uuid4()}",
        capture_date="2026-08-12",
        capture_date_dt=date(2026, 8, 12),
        is_set_based=True,
        lab_unit_id=lab_unit.id,
    )
    image = EncounterSetImage(
        patient_encounter=encounter,
        spatial_position=1,
        original_filename=f"{uuid4()}.png",
        folder_rel="wadhwani-page-tests",
        hospital_id=lab_unit.hospital_id,
    )
    task = GradingTask(
        encounter_set_image=image,
        disease_id=core_test_data["glaucoma"].id,
        lab_unit_id=lab_unit.id,
        state="pending",
        grading_target_level="image",
    )
    model = AIModel(name=f"Positive WAI model {uuid4()}", version="test")
    db_session.add_all([encounter, image, task, model])
    db_session.flush()
    run = AIInferenceRun(
        task_id=task.id,
        ai_model_id=model.id,
        source="internal",
        status="success",
        execute_response_json={
            "results": [{"predicted_class": 1, "predicted_class_name": "Glaucoma Present"}]
        },
    )
    job = Job(
        token=f"positive-{uuid4().hex}",
        status="done",
        upload_type="encounter_set_wadhwani_inference",
        lab_unit_id=lab_unit.id,
    )
    db_session.add_all([run, job])
    db_session.flush()
    db_session.add(
        JobItem(
            job_id=job.id,
            filename=f"task:{task.id}",
            task_id=task.id,
            state="ok",
            detail=json.dumps({"inference_run_id": run.id}),
        )
    )
    db_session.flush()
    login_user("test_admin", "Test@2026")

    response = client.get(f"/uploads/encountersets/wadhwani_inference/jobs/{job.token}/status")

    assert response.status_code == 286
    assert b"Positive inference" in response.data
    assert b"Glaucoma Present" in response.data
    assert b"fs-4 text-danger\">1<" in response.data


def test_recent_encounter_set_jobs_api_returns_latest_ten_scoped_jobs(
    client,
    login_user,
    db_session,
    core_test_data,
):
    project = Project(title=f"Recent WAI {uuid4()}", code=f"RW{uuid4().hex[:8]}", active=True)
    other_project = Project(title=f"Other WAI {uuid4()}", code=f"OW{uuid4().hex[:8]}", active=True)
    db_session.add_all([project, other_project])
    db_session.flush()
    base_time = utcnow()
    tokens = []
    for index in range(11):
        token = f"recent-{index}-{uuid4().hex}"
        tokens.append(token)
        job = Job(
            token=token,
            status="done",
            upload_type="encounter_set_wadhwani_inference",
            project_id=project.id,
            lab_unit_id=core_test_data["lab_unit"].id,
            created_at=base_time + timedelta(minutes=index),
        )
        job.items.append(JobItem(filename=f"task:{index + 1}", state="ok"))
        db_session.add(job)
    encounter = PatientEncounters(
        name=f"Recent WAI scoped {uuid4()}",
        patient_id=f"patient-{uuid4()}",
        capture_date="2026-08-12",
        capture_date_dt=date(2026, 8, 12),
        is_set_based=True,
        project_id=project.id,
        lab_unit_id=core_test_data["lab_unit"].id,
    )
    image = EncounterSetImage(
        patient_encounter=encounter,
        spatial_position=1,
        original_filename=f"{uuid4()}.png",
        folder_rel="wadhwani-recent-jobs",
        hospital_id=core_test_data["lab_unit"].hospital_id,
    )
    task = GradingTask(
        encounter_set_image=image,
        disease_id=core_test_data["glaucoma"].id,
        lab_unit_id=core_test_data["lab_unit"].id,
        state="pending",
        grading_target_level="image",
    )
    db_session.add_all([encounter, image, task])
    db_session.flush()
    null_job_lab_token = f"null-job-lab-{uuid4().hex}"
    null_job_lab = Job(
        token=null_job_lab_token,
        status="done",
        upload_type="encounter_set_wadhwani_inference",
        project_id=project.id,
        lab_unit_id=None,
        created_at=base_time + timedelta(minutes=12),
    )
    null_job_lab.items.append(JobItem(filename=f"task:{task.id}", task_id=task.id, state="ok"))
    db_session.add(null_job_lab)
    db_session.add(
        Job(
            token=f"other-{uuid4().hex}",
            status="done",
            upload_type="encounter_set_wadhwani_inference",
            project_id=other_project.id,
            lab_unit_id=core_test_data["lab_unit"].id,
        )
    )
    db_session.flush()
    login_user("test_admin", "Test@2026")

    response = client.get(
        f"/api/remote-inference/projects/{project.id}/wadhwani/encounter-set-jobs"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["jobs"]) == 10
    assert payload["jobs"][0]["token"] == null_job_lab_token
    assert tokens[0] not in {row["token"] for row in payload["jobs"]}
    assert payload["jobs"][0]["total_count"] == 1

    fragment = client.get(
        f"/api/remote-inference/projects/{project.id}/wadhwani/encounter-set-jobs",
        headers={"HX-Request": "true"},
    )
    assert fragment.status_code == 200
    assert null_job_lab_token.encode() in fragment.data
    assert b"/uploads/encountersets/wadhwani_inference/jobs/" in fragment.data
