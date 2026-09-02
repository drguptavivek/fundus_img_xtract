import grading.workbench_page as workbench_page_module
from grading.workbench.errors import NoEligibleWork
from models import EncounterFile, GradingTask, UserDiseaseUnitRole
from tests.helpers.factories import UserFactory
from tests.helpers.test_factories import TestDataFactory


class TestNextTaskMessagePreference:
    def test_field_ophthalmologist_reaches_web_grading_gate_but_field_optometrist_does_not(
        self, app, db_session, core_test_data, monkeypatch
    ):
        lab_unit = db_session.merge(core_test_data["lab_unit"])
        field_ophthalmologist = UserFactory.create_by_role(
            db_session,
            "field_ophthalmologist",
            username="grading_web_field_ophthalmologist",
            lab_units=[lab_unit],
        )
        field_optometrist = UserFactory.create_by_role(
            db_session,
            "field_optometrist",
            username="grading_web_field_optometrist",
            lab_units=[lab_unit],
        )
        db_session.add(
            UserDiseaseUnitRole(
                user_id=field_ophthalmologist.id,
                disease_id=core_test_data["glaucoma"].id,
                lab_unit_id=lab_unit.id,
                can_grade_resident=True,
            )
        )
        db_session.flush()

        # Acquisition is owned by the shared workbench_page helpers (also used
        # by the grader PWA), so the seam to stub is there.
        monkeypatch.setattr(
            workbench_page_module,
            "acquire_next_workbench",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                NoEligibleWork("Resident queue empty")
            ),
        )

        field_client = app.test_client(user=field_ophthalmologist)
        field_response = field_client.get(
            f"/grading/grade/{core_test_data['glaucoma'].id}/resident",
            follow_redirects=False,
        )
        assert field_response.status_code in (302, 303)

        assert not field_optometrist.has_role(
            "resident", "ophthalmologist", "field_ophthalmologist"
        )

    def test_start_grading_surfaces_workbench_queue_message(
        self, auth_client, ophthalmologist_hospital_a, core_test_data, monkeypatch
    ):
        resident_message = "Resident queue empty"
        # Acquisition is owned by the shared workbench_page helpers (also used
        # by the grader PWA), so the seam to stub is there.
        monkeypatch.setattr(
            workbench_page_module,
            "acquire_next_workbench",
            lambda *args, **kwargs: (_ for _ in ()).throw(NoEligibleWork(resident_message)),
        )

        client = auth_client(ophthalmologist_hospital_a)
        response = client.get(
            f"/grading/grade/{core_test_data['glaucoma'].id}/resident",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert resident_message in response.get_data(as_text=True)

    def test_legacy_save_next_delegates_to_workbench_and_returns_to_queue(
        self,
        auth_client,
        ophthalmologist_hospital_a,
        hospital_data,
        disease_grading_glaucoma_normal,
        core_test_data,
        db_session,
        monkeypatch,
    ):
        user = db_session.merge(ophthalmologist_hospital_a)
        user_lab_unit = user.lab_units[0]
        hospital = user_lab_unit.hospital

        encounter = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=user_lab_unit.id,
            patient_id="PATIENT_A_GRADING",
        )

        encounter_file = EncounterFile(
            filename="grading_task_image.jpg",
            patient_encounter_id=encounter.id,
            file_type="image",
            lab_unit_id=user_lab_unit.id,
            hospital_id=hospital.id,
        )
        db_session.add(encounter_file)
        db_session.flush()

        task = GradingTask(
            encounter_file_id=encounter_file.id,
            disease_id=core_test_data["glaucoma"].id,
            lab_unit_id=user_lab_unit.id,
            state="pending",
        )
        db_session.add(task)
        db_session.flush()

        user_role = UserDiseaseUnitRole(
            user_id=user.id,
            disease_id=core_test_data["glaucoma"].id,
            lab_unit_id=user_lab_unit.id,
            can_grade_resident=True,
        )
        db_session.add(user_role)
        db_session.flush()

        client = auth_client(ophthalmologist_hospital_a)
        response = client.post(
            "/grading/task/submit",
            data={
                "task_uuid": task.uuid,
                "slot": "resident",
                "label_id": disease_grading_glaucoma_normal.id,
                "action": "save_next",
            },
            follow_redirects=False,
        )

        assert response.status_code in (302, 303)
        assert f"/grading/grade/{task.disease_id}/resident" in response.headers["Location"]
