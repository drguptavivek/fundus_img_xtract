import pytest
from sqlalchemy import select
from models import (
    Session, DirectImageUpload, DirectImageVerify, EncounterFile, 
    PatientEncounters, Disease, GradingTask, LabUnit, Hospital, Camera, Area, ZipFile,
    DiabeticRetinopathyReport, GlaucomaResultsCleaned
)


class TestVerificationSafety:
    """Test suite for verification safety checks."""

    def test_dr_unverify_blocked_with_non_pending_tasks(self, setup_test_data):
        """Test that DR unverification is blocked when tasks are not pending."""
        db = Session()
        try:
            # Create test data for DR verification
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
                capture_date="2023-01-01",
                dr_verified_status='verified'  # Initially verified
            )
            db.add(encounter)
            db.flush()
            
            # Create test encounter file
            encounter_file = EncounterFile(
                patient_encounter_id=encounter.id,
                filename="test_image.png",
                file_type="image/png",
                uuid="123e4567-e89b-12d3-a456-426614174000"
            )
            db.add(encounter_file)
            db.flush()
            
            # Create a grading task for this encounter file
            dr_disease = Disease(name="Diabetic Retinopathy")
            db.add(dr_disease)
            db.flush()
            
            task = GradingTask(
                encounter_file_id=encounter_file.id,
                disease_id=dr_disease.id,
                lab_unit_id=lab_unit.id,
                state='resident_done'  # Non-pending state
            )
            db.add(task)
            db.commit()
            
            # Try to unverify - should be blocked
            from services.taskCreationServices import can_unverify_image
            can_unverify = can_unverify_image(db, kind='encounter', image_id=encounter_file.id)
            assert can_unverify is False
            
        finally:
            db.rollback()
            db.close()

    def test_glaucoma_unverify_blocked_with_non_pending_tasks(self, setup_test_data):
        """Test that Glaucoma unverification is blocked when tasks are not pending."""
        db = Session()
        try:
            # Create test data for Glaucoma verification
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
                capture_date="2023-01-01",
                glaucoma_verified_status='verified'  # Initially verified
            )
            db.add(encounter)
            db.flush()
            
            # Create test encounter file
            encounter_file = EncounterFile(
                patient_encounter_id=encounter.id,
                filename="test_image.png",
                file_type="image/png",
                uuid="123e4567-e89b-12d3-a456-426614174001"
            )
            db.add(encounter_file)
            db.flush()
            
            # Create a grading task for this encounter file
            glaucoma_disease = Disease(name="Glaucoma")
            db.add(glaucoma_disease)
            db.flush()
            
            task = GradingTask(
                encounter_file_id=encounter_file.id,
                disease_id=glaucoma_disease.id,
                lab_unit_id=lab_unit.id,
                state='faculty_done'  # Non-pending state
            )
            db.add(task)
            db.commit()
            
            # Try to unverify - should be blocked
            from services.taskCreationServices import can_unverify_image
            can_unverify = can_unverify_image(db, kind='encounter', image_id=encounter_file.id)
            assert can_unverify is False
            
        finally:
            db.rollback()
            db.close()

    def test_dr_unverify_allowed_with_pending_tasks(self, setup_test_data):
        """Test that DR unverification is allowed when all tasks are pending."""
        db = Session()
        try:
            # Create test data for DR verification
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
                capture_date="2023-01-01",
                dr_verified_status='verified'  # Initially verified
            )
            db.add(encounter)
            db.flush()
            
            # Create test encounter file
            encounter_file = EncounterFile(
                patient_encounter_id=encounter.id,
                filename="test_image.png",
                file_type="image/png",
                uuid="123e4567-e89b-12d3-a456-426614174002"
            )
            db.add(encounter_file)
            db.flush()
            
            # Create a grading task for this encounter file (pending state)
            dr_disease = Disease(name="Diabetic Retinopathy")
            db.add(dr_disease)
            db.flush()
            
            task = GradingTask(
                encounter_file_id=encounter_file.id,
                disease_id=dr_disease.id,
                lab_unit_id=lab_unit.id,
                state='pending'  # Pending state
            )
            db.add(task)
            db.commit()
            
            # Try to unverify - should be allowed
            from services.taskCreationServices import can_unverify_image
            can_unverify = can_unverify_image(db, kind='encounter', image_id=encounter_file.id)
            assert can_unverify is True
            
        finally:
            db.rollback()
            db.close()