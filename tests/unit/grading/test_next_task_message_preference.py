import pytest

from models import EncounterFile, GradingTask
from tests.helpers.test_factories import TestDataFactory
import grading.start_grading as start_grading_module
import grading.dual_grading as dual_grading_module


@pytest.mark.integration
class TestNextTaskMessagePreference:
    def test_start_grading_prefers_resident_message(
        self, auth_client, ophthalmologist_hospital_a, core_test_data, monkeypatch
    ):
        resident_message = "Resident queue empty"
        resident2_message = "Resident2 queue empty"

        monkeypatch.setattr(
            start_grading_module,
            "get_next_eligible_resident2_task_atomic",
            lambda *args, **kwargs: resident2_message,
        )
        monkeypatch.setattr(
            start_grading_module,
            "get_next_eligible_resident_task_atomic",
            lambda *args, **kwargs: resident_message,
        )

        client = auth_client(ophthalmologist_hospital_a)
        response = client.get(
            f"/grade/{core_test_data['glaucoma'].id}/resident",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert resident_message in response.get_data(as_text=True)
        assert resident2_message not in response.get_data(as_text=True)

    def test_save_next_prefers_resident_message(
        self,
        auth_client,
        ophthalmologist_hospital_a,
        hospital_data,
        disease_grading_glaucoma_normal,
        core_test_data,
        db_session,
        monkeypatch,
    ):
        encounter = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            patient_id="PATIENT_A_GRADING",
        )

        encounter_file = EncounterFile(
            filename="grading_task_image.jpg",
            patient_encounter_id=encounter.id,
            file_type="image",
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            hospital_id=hospital_data["hospital_a"]["hospital"].id,
        )
        db_session.add(encounter_file)
        db_session.flush()

        task = GradingTask(
            encounter_file_id=encounter_file.id,
            disease_id=core_test_data["glaucoma"].id,
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            state="pending",
        )
        db_session.add(task)
        db_session.flush()

        resident_message = "Resident queue empty"
        resident2_message = "Resident2 queue empty"

        monkeypatch.setattr(dual_grading_module, "get_next_intra_rater_task", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            dual_grading_module,
            "get_next_eligible_resident2_task_atomic",
            lambda *args, **kwargs: resident2_message,
        )
        monkeypatch.setattr(
            dual_grading_module,
            "get_next_eligible_resident_task_atomic",
            lambda *args, **kwargs: resident_message,
        )

        client = auth_client(ophthalmologist_hospital_a)
        response = client.post(
            "/grading/task/submit",
            data={
                "task_uuid": task.uuid,
                "slot": "resident",
                "label_id": disease_grading_glaucoma_normal.id,
                "action": "save_next",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert resident_message in body
        assert resident2_message not in body
