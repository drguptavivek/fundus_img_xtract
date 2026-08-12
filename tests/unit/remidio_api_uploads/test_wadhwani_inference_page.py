from __future__ import annotations

import json
from datetime import date
from datetime import timedelta
from types import SimpleNamespace
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
    _wadhwani_status_by_image,
)


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
