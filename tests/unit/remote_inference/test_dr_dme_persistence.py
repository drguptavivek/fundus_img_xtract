from __future__ import annotations

from datetime import date
from contextlib import contextmanager
from uuid import uuid4

from PIL import Image
from sqlalchemy import select

from models import AIModelIntegration, EncounterSetImage, Grade, GradingTask, PatientEncounters, Project
from remote_inference import dr_dme_service
from remote_inference.models import EncounterAIImageResult, EncounterAIInferenceRun, EncounterAITargetResult


class Client:
    def __init__(self):
        self.submit_calls = 0

    def presign(self, *, request_id, images):
        return {
            "request_id": request_id,
            "uploads": [
                {
                    "eye": row["eye"],
                    "key": f"inference/{request_id}/{row['eye']}/{index}.jpg",
                    "original_filename": row["original_filename"],
                    "content_type": "image/jpeg",
                    "upload_url": f"https://storage.example/{index}?signature=secret",
                }
                for index, row in enumerate(images, start=1)
            ],
        }

    def upload(self, **kwargs):
        assert set(kwargs) == {"upload_url", "content_type", "image_bytes"}
        return 1

    def submit(self, *, request_id, patient, images):
        self.submit_calls += 1
        return {
            "report_id": "report-1",
            "request_id": request_id,
            "patient_id": patient["patient_id"],
            "status": "completed",
            "results": {
                "images": {
                    "left": [],
                    "right": [
                        {
                            "key": images[0]["key"],
                            "filename": images[0]["original_filename"],
                            "is_primary": True,
                            "model_outputs": {
                                "eyes": {"eyes_label": "right_eye"},
                                "drdme": {
                                    "DR_grade": "Mild NPDR",
                                    "DR_score": 0.25,
                                    "DME_grade": "No DME",
                                    "DME_score": -0.15,
                                },
                                "similarity_score": 20.0,
                            },
                        }
                    ],
                }
            },
        }


def test_encounter_response_persists_two_target_grades_and_reuses_report(
    db_session, core_test_data, tmp_path, monkeypatch
):
    integration = db_session.execute(
        select(AIModelIntegration).where(AIModelIntegration.provider == "wai_dr_dme")
    ).scalar_one()
    integration.is_enabled = True
    project = Project(title=f"MadhuNetrAI {uuid4()}", code=f"MDN{str(uuid4())[:8]}", active=True)
    db_session.add(project)
    db_session.flush()
    encounter = PatientEncounters(
        name="MadhuNetrAI test",
        patient_id="UHID-123",
        capture_date="2026-08-18",
        capture_date_dt=date(2026, 8, 18),
        is_set_based=True,
        lab_unit_id=core_test_data["lab_unit"].id,
        project_id=project.id,
        encounter_verified_status="verified",
        metadata_json={"age": 58, "sex": "female"},
    )
    db_session.add(encounter)
    db_session.flush()
    folder = tmp_path / "images"
    folder.mkdir()
    filename = f"{uuid4()}.jpg"
    Image.new("RGB", (8, 8), "white").save(folder / filename, format="JPEG")
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename=filename,
        folder_rel="images",
        hospital_id=core_test_data["hospital"].id,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        metadata_json={"laterality": "OD", "focus": "MACULA"},
    )
    db_session.add(image)
    db_session.flush()
    monkeypatch.setattr(dr_dme_service, "BASE_DIR", tmp_path)

    @contextmanager
    def same_session():
        yield db_session

    monkeypatch.setattr(dr_dme_service, "transaction_scope", same_session)
    client = Client()

    result = dr_dme_service.run_encounter_inference(
        encounter_id=encounter.id,
        requested_by_user_id=None,
        source="manual",
        client=client,
    )
    reused = dr_dme_service.run_encounter_inference(
        encounter_id=encounter.id,
        requested_by_user_id=None,
        source="manual",
        client=client,
    )

    assert result.status == "success"
    assert result.report_id == "report-1"
    assert reused.reused is True
    assert client.submit_calls == 1
    run = db_session.get(EncounterAIInferenceRun, result.run_id)
    assert "upload_url" not in str(run.presign_response_json)
    assert "signature" not in str(run.presign_response_json)
    image_result = db_session.execute(
        select(EncounterAIImageResult).where(EncounterAIImageResult.run_id == run.id)
    ).scalar_one()
    assert image_result.is_primary is True
    assert image_result.laterality_mismatch is False
    targets = db_session.execute(
        select(EncounterAITargetResult).where(EncounterAITargetResult.image_result_id == image_result.id)
    ).scalars().all()
    assert {row.raw_score for row in targets} == {0.25, -0.15}
    tasks = db_session.execute(
        select(GradingTask).where(GradingTask.encounter_set_image_id == image.id)
    ).scalars().all()
    assert len(tasks) == 2
    grades = db_session.execute(select(Grade).where(Grade.task_id.in_([task.id for task in tasks]))).scalars().all()
    assert {grade.grade_name for grade in grades} == {"Mild DR", "M0 No DME"}
    assert all(grade.ai_model_id == integration.ai_model_id for grade in grades)
