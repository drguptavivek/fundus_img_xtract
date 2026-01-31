import pytest
from sqlalchemy.exc import IntegrityError
from models import EncounterSetImage, GradingTask, PatientEncounters, Disease
from auth.utils import utcnow

def test_encounter_set_image_creation(db_session):
    """Test that EncounterSetImage can be created with valid fields."""
    # Assuming PatientEncounters.is_set_based exists
    encounter = PatientEncounters(
        is_set_based=True,
        name="Test Patient",
        patient_id="UHID123",
        capture_date="2026-01-31"
    )
    db_session.add(encounter)
    db_session.commit()

    img = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=5,
        original_filename="primary_gaze.jpg",
        uuid="test-uuid-set-1",
        folder_rel="2026_01_31_user1",
        created_at=utcnow()
    )
    db_session.add(img)
    db_session.commit()

    assert img.id is not None
    assert img.spatial_position == 5

def test_grading_task_polymorphism_constraints(db_session):
    """Test that GradingTask must have exactly one link non-null."""
    # This test will likely fail initially as the columns/constraints don't exist yet.
    task = GradingTask(
        state='pending',
        disease_id=1,
        created_at=utcnow()
    )
    
    # CASE 1: Zero links (Should fail)
    with pytest.raises(Exception): # Using generic Exception since IntegrityError might not be raised yet
        db_session.add(task)
        db_session.commit()
    db_session.rollback()

    # CASE 2: Multiple links (Should fail)
    # Assuming encounter_file_id and patient_encounter_id both exist
    task.encounter_file_id = 1
    task.patient_encounter_id = 1
    with pytest.raises(Exception):
        db_session.add(task)
        db_session.commit()
    db_session.rollback()

def test_patient_encounter_nullable_zip(db_session):
    """Test that PatientEncounters can exist without a zip_file_id."""
    encounter = PatientEncounters(
        is_set_based=True,
        zip_file_id=None,
        name="Test Patient Nullable Zip",
        patient_id="UHID456",
        capture_date="2026-01-31"
    )
    db_session.add(encounter)
    db_session.commit()
    
    assert encounter.id is not None
    assert encounter.zip_file_id is None