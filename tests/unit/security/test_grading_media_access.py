import uuid

import pytest

from models import EncounterFile, GradingTask, UserDiseaseUnitRole
import utils.utilsImgServe as img_serve
from tests.helpers.test_factories import TestDataFactory


@pytest.mark.integration
class TestGradingMediaAccess:
    def test_grading_media_allows_cross_hospital_slot_access(
        self, auth_client, hospital_data, core_test_data, db_session, cross_grader_a_to_b, monkeypatch, tmp_path
    ):
        image_root = tmp_path / "zip_upload_images"
        image_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(img_serve, "IMAGE_DIR", image_root)

        encounter = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            patient_id="PATIENT_B_GRADING",
        )

        image_uuid = str(uuid.uuid4())
        filename = "grading_cross_hospital.jpg"
        encounter_file = EncounterFile(
            uuid=image_uuid,
            filename=filename,
            patient_encounter_id=encounter.id,
            file_type="image",
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            hospital_id=hospital_data["hospital_b"]["hospital"].id,
        )
        db_session.add(encounter_file)
        db_session.flush()

        task = GradingTask(
            encounter_file_id=encounter_file.id,
            disease_id=core_test_data["glaucoma"].id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            state="pending",
        )
        db_session.add(task)
        db_session.flush()

        existing_perm = (
            db_session.query(UserDiseaseUnitRole)
            .filter(
                UserDiseaseUnitRole.user_id == cross_grader_a_to_b.id,
                UserDiseaseUnitRole.disease_id == core_test_data["glaucoma"].id,
                UserDiseaseUnitRole.lab_unit_id == hospital_data["hospital_b"]["lab_units"][0].id,
            )
            .first()
        )
        if not existing_perm:
            db_session.add(
                UserDiseaseUnitRole(
                    user_id=cross_grader_a_to_b.id,
                    disease_id=core_test_data["glaucoma"].id,
                    lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
                    can_grade_resident=True,
                    can_grade_resident2=True,
                    can_arbitrate=False,
                )
            )
            db_session.flush()

        upload_date_str = encounter.zip_file.upload_date.strftime("%Y_%m_%d")
        image_dir = image_root / upload_date_str
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / filename
        image_path.write_bytes(b"fake-image")

        try:
            client = auth_client(cross_grader_a_to_b)
            response = client.get(f"/media/img/{image_uuid}")
            assert response.status_code == 200
        finally:
            if image_path.exists():
                image_path.unlink()

    def test_grading_media_blocks_without_slot_or_lab_unit(
        self, auth_client, hospital_data, core_test_data, db_session, ophthalmologist_hospital_a, monkeypatch, tmp_path
    ):
        image_root = tmp_path / "zip_upload_images"
        image_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(img_serve, "IMAGE_DIR", image_root)

        encounter = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            patient_id="PATIENT_B_NO_ACCESS",
        )

        image_uuid = str(uuid.uuid4())
        filename = "grading_no_access.jpg"
        encounter_file = EncounterFile(
            uuid=image_uuid,
            filename=filename,
            patient_encounter_id=encounter.id,
            file_type="image",
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            hospital_id=hospital_data["hospital_b"]["hospital"].id,
        )
        db_session.add(encounter_file)
        db_session.flush()

        task = GradingTask(
            encounter_file_id=encounter_file.id,
            disease_id=core_test_data["glaucoma"].id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            state="pending",
        )
        db_session.add(task)
        db_session.flush()

        upload_date_str = encounter.zip_file.upload_date.strftime("%Y_%m_%d")
        image_dir = image_root / upload_date_str
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / filename
        image_path.write_bytes(b"fake-image")

        try:
            client = auth_client(ophthalmologist_hospital_a)
            response = client.get(f"/media/img/{image_uuid}")
            assert response.status_code == 404
        finally:
            if image_path.exists():
                image_path.unlink()
