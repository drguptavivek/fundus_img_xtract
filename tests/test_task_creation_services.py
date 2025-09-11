import pytest
from sqlalchemy import select
from models import (
    Session, DirectImageUpload, DirectImageVerify, EncounterFile, 
    PatientEncounters, Disease, GradingTask, LabUnit, Hospital, Camera, Area, ZipFile
)
from services.taskCreationServices import (
    _resolve_image_by_uuid, _is_verified_for_disease, can_unverify_image, 
    create_or_get_task, remove_pending_tasks, ensure_task
)
from unittest.mock import patch


class TestTaskCreationServices:
    """Test suite for task creation services."""

    def test_resolve_image_by_uuid_direct(self, setup_test_data):
        """Test resolving a direct image by UUID."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174000",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            # Test resolution
            kind, image_id, lab_unit_id = _resolve_image_by_uuid(db, "123e4567-e89b-12d3-a456-426614174000")
            assert kind == "direct"
            assert image_id == upload.id
            assert lab_unit_id == lab_unit.id
        finally:
            db.rollback()
            db.close()

    def test_resolve_image_by_uuid_encounter(self, setup_test_data):
        """Test resolving an encounter file by UUID."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            encounter = PatientEncounters(
                zip_file_id=zip_file.id,
                name="Test Patient",
                patient_id="TEST001"
            )
            db.add(encounter)
            db.flush()
            
            encounter_file = EncounterFile(
                patient_encounter_id=encounter.id,
                filename="test_image.png",
                file_type="image/png",
                uuid="123e4567-e89b-12d3-a456-426614174001"
            )
            db.add(encounter_file)
            db.flush()
            
            # Test resolution
            kind, image_id, lab_unit_id = _resolve_image_by_uuid(db, "123e4567-e89b-12d3-a456-426614174001")
            assert kind == "encounter"
            assert image_id == encounter_file.id
            assert lab_unit_id == lab_unit.id
        finally:
            db.rollback()
            db.close()

    def test_resolve_image_by_uuid_not_found(self, setup_test_data):
        """Test resolving a non-existent image by UUID."""
        db = Session()
        try:
            with pytest.raises(ValueError, match="Image not found"):
                _resolve_image_by_uuid(db, "123e4567-e89b-12d3-a456-426614174002")
        finally:
            db.rollback()
            db.close()

    def test_is_verified_for_disease_direct_verified(self, setup_test_data):
        """Test verification check for a verified direct image."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174003",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            verification = DirectImageVerify(
                image_upload_id=upload.id,
                verified_status="verified"
            )
            db.add(verification)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Test verification check
            result = _is_verified_for_disease(db, "direct", upload.id, disease.id)
            assert result is True
        finally:
            db.rollback()
            db.close()

    def test_is_verified_for_disease_direct_not_verified(self, setup_test_data):
        """Test verification check for a non-verified direct image."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174004",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Test verification check
            result = _is_verified_for_disease(db, "direct", upload.id, disease.id)
            assert result is False
        finally:
            db.rollback()
            db.close()

    def test_is_verified_for_disease_encounter_dr_verified(self, setup_test_data):
        """Test verification check for a DR-verified encounter."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            encounter = PatientEncounters(
                zip_file_id=zip_file.id,
                name="Test Patient",
                patient_id="TEST001",
                dr_verified_status="verified"
            )
            db.add(encounter)
            db.flush()
            
            encounter_file = EncounterFile(
                patient_encounter_id=encounter.id,
                filename="test_image.png",
                file_type="image/png",
                uuid="123e4567-e89b-12d3-a456-426614174005"
            )
            db.add(encounter_file)
            db.flush()
            
            disease = Disease(name="Diabetic Retinopathy")
            db.add(disease)
            db.flush()
            
            # Test verification check
            result = _is_verified_for_disease(db, "encounter", encounter_file.id, disease.id)
            assert result is True
        finally:
            db.rollback()
            db.close()

    def test_is_verified_for_disease_encounter_dr_not_verified(self, setup_test_data):
        """Test verification check for a non-DR-verified encounter."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            encounter = PatientEncounters(
                zip_file_id=zip_file.id,
                name="Test Patient",
                patient_id="TEST001"
            )
            db.add(encounter)
            db.flush()
            
            encounter_file = EncounterFile(
                patient_encounter_id=encounter.id,
                filename="test_image.png",
                file_type="image/png",
                uuid="123e4567-e89b-12d3-a456-426614174006"
            )
            db.add(encounter_file)
            db.flush()
            
            disease = Disease(name="Diabetic Retinopathy")
            db.add(disease)
            db.flush()
            
            # Test verification check
            result = _is_verified_for_disease(db, "encounter", encounter_file.id, disease.id)
            assert result is False
        finally:
            db.rollback()
            db.close()

    def test_create_or_get_task_new_task(self, setup_test_data):
        """Test creating a new task."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174007",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Test task creation
            task = create_or_get_task(db, kind="direct", image_id=upload.id, disease_id=disease.id, lab_unit_id=lab_unit.id)
            assert task.direct_image_upload_id == upload.id
            assert task.disease_id == disease.id
            assert task.lab_unit_id == lab_unit.id
            assert task.state == "pending"
        finally:
            db.rollback()
            db.close()

    def test_create_or_get_task_existing_task(self, setup_test_data):
        """Test getting an existing task."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit1 = LabUnit(name="Test Lab Unit 1", hospital_id=hospital.id)
            db.add(lab_unit1)
            db.flush()
            
            lab_unit2 = LabUnit(name="Test Lab Unit 2", hospital_id=hospital.id)
            db.add(lab_unit2)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174008",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit1.id
            )
            db.add(upload)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Create initial task
            initial_task = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease.id,
                lab_unit_id=lab_unit1.id,
                state="pending"
            )
            db.add(initial_task)
            db.commit()
            
            # Try to create another task for the same image×disease
            # Should return the existing task, not create a new one
            task = create_or_get_task(db, kind="direct", image_id=upload.id, disease_id=disease.id, lab_unit_id=lab_unit2.id)
            assert task.id == initial_task.id
            assert task.lab_unit_id == lab_unit1.id  # Should not change
            assert task.state == "pending"
        finally:
            db.rollback()
            db.close()

    def test_can_unverify_image_all_pending(self, setup_test_data):
        """Test can_unverify_image with all pending tasks."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174009",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Create pending task
            task = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease.id,
                lab_unit_id=lab_unit.id,
                state="pending"
            )
            db.add(task)
            db.commit()
            
            # Test can_unverify
            result = can_unverify_image(db, kind="direct", image_id=upload.id)
            assert result is True
        finally:
            db.rollback()
            db.close()

    def test_can_unverify_image_non_pending(self, setup_test_data):
        """Test can_unverify_image with non-pending tasks."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174010",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Create non-pending task
            task = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease.id,
                lab_unit_id=lab_unit.id,
                state="resident_done"
            )
            db.add(task)
            db.commit()
            
            # Test can_unverify
            result = can_unverify_image(db, kind="direct", image_id=upload.id)
            assert result is False
        finally:
            db.rollback()
            db.close()

    def test_remove_pending_tasks(self, setup_test_data):
        """Test removing pending tasks."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174011",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Create pending task
            task1 = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease.id,
                lab_unit_id=lab_unit.id,
                state="pending"
            )
            db.add(task1)
            
            # Create non-pending task
            task2 = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease.id,
                lab_unit_id=lab_unit.id,
                state="resident_done"
            )
            db.add(task2)
            db.commit()
            
            # Test task removal
            removed_count = remove_pending_tasks(db, kind="direct", image_id=upload.id)
            assert removed_count == 1
            
            # Verify only pending task was removed
            remaining_tasks = db.execute(
                select(GradingTask).where(GradingTask.direct_image_upload_id == upload.id)
            ).scalars().all()
            assert len(remaining_tasks) == 1
            assert remaining_tasks[0].state == "resident_done"
        finally:
            db.rollback()
            db.close()

    def test_ensure_task_cross_lab_reassignment_blocked_for_final_task(self, setup_test_data):
        """Test that cross-lab reassignment is blocked for final tasks."""
        db = Session()
        try:
            # Create test data with two different lab units
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit1 = LabUnit(name="Test Lab Unit 1", hospital_id=hospital.id)
            db.add(lab_unit1)
            db.flush()
            
            lab_unit2 = LabUnit(name="Test Lab Unit 2", hospital_id=hospital.id)
            db.add(lab_unit2)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            # Create direct image upload with lab_unit1
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174012",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit1.id
            )
            db.add(upload)
            db.flush()
            
            # Create verification
            verification = DirectImageVerify(
                image_upload_id=upload.id,
                verified_status="verified"
            )
            db.add(verification)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Create a final task with lab_unit1
            task = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease.id,
                lab_unit_id=lab_unit1.id,
                state="final"
            )
            db.add(task)
            db.commit()
            
            # Mock the _resolve_image_by_uuid function to return lab_unit2
            # This simulates trying to access the same image from a different lab
            with patch('services.taskCreationServices._resolve_image_by_uuid') as mock_resolve:
                mock_resolve.return_value = ("direct", upload.id, lab_unit2.id)
                
                # Try to ensure task from different lab - should raise PermissionError
                with pytest.raises(PermissionError, match="Gold standard already set - cross-lab reassignment is disabled for finalized tasks"):
                    ensure_task("123e4567-e89b-12d3-a456-426614174012", disease.id)
        finally:
            db.rollback()
            db.close()

    def test_ensure_task_success_with_same_lab_for_final_task(self, setup_test_data):
        """Test that accessing a final task from the same lab succeeds."""
        db = Session()
        try:
            # Create test data
            hospital = Hospital(name="Test Hospital")
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name="Test Camera")
            db.add(camera)
            db.flush()
            
            area = Area(name="Test Area")
            db.add(area)
            db.flush()
            
            zip_file = ZipFile(
                zip_filename="test.zip",
                md5_hash="test_hash"
            )
            db.add(zip_file)
            db.flush()
            
            # Create direct image upload
            upload = DirectImageUpload(
                uuid="123e4567-e89b-12d3-a456-426614174013",
                filename="test_image.png",
                file_type="image/png",
                camera_id=camera.id,
                area_id=area.id,
                zip_file_id=zip_file.id,
                lab_unit_id=lab_unit.id
            )
            db.add(upload)
            db.flush()
            
            # Create verification
            verification = DirectImageVerify(
                image_upload_id=upload.id,
                verified_status="verified"
            )
            db.add(verification)
            db.flush()
            
            disease = Disease(name="Glaucoma")
            db.add(disease)
            db.flush()
            
            # Create a final task
            task = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease.id,
                lab_unit_id=lab_unit.id,
                state="final"
            )
            db.add(task)
            db.commit()
            
            # Try to ensure task from the same lab - should succeed
            result_task = ensure_task("123e4567-e89b-12d3-a456-426614174013", disease.id)
            assert result_task.id == task.id
            assert result_task.state == "final"
            assert result_task.lab_unit_id == lab_unit.id
        finally:
            db.rollback()
            db.close()