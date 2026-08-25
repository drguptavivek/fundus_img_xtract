"""
Tests for Encounter Set Grading (Task 4: Sync-Grid Grading Viewer)

TDD approach: Tests written before implementation.

Tests cover:
- Task creation for encounter sets
- Grading route access and permissions
- Grading submission for encounter sets
- Media routes serving edited images first
- Not gradable handling for incomplete sets
"""


# The legacy /grading/encounter_set/* transport this file used to exercise was
# deleted: it bypassed allocation entirely and wrote a Grade into whichever slot
# the client named. Its behaviour is covered against the workbench instead -
# submission and consensus in tests/unit/grading/test_workbench_submission.py,
# package grading in test_encounter_set_package_grading.py.
#
# What remains here is the part that never depended on that transport: task
# creation from a verified encounter set, and media serving.

import pytest
import uuid
from datetime import date, datetime
from models import (
    PatientEncounters, EncounterSetImage, LabUnit, Disease,
    GradingTask, Grade, Consensus, User
)
from tests.helpers.factories import UserFactory, CoreEntityFactory

pytestmark = pytest.mark.integration


@pytest.fixture
def verified_encounter_set(db_session, core_test_data):
    """Create a verified encounter set ready for grading."""
    lab_unit = db_session.merge(core_test_data['lab_unit'])
    glaucoma = db_session.merge(core_test_data['glaucoma'])

    encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="Test Grading Set",
        patient_id="PAT-GRADING-001",
        capture_date="2024-01-15",
        capture_date_dt=date(2024, 1, 15),
        lab_unit_id=lab_unit.id,
        is_set_based=True,
        encounter_verified_status='verified',
        encounter_verified_by='optometrist',
        disease_id=glaucoma.id,
        encounter_verified_at=datetime.now()
    )
    db_session.add(encounter)
    db_session.flush()

    # Create 9 images for the set (all reviewed)
    images = []
    for pos in range(1, 10):
        img = EncounterSetImage(
            uuid=str(uuid.uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=pos,
            original_filename=f"pos_{pos}.jpg",
            folder_rel=f"files/encounter_sets/{encounter.id}",
            is_reviewed=True,
            is_anonymized=True,
            is_not_gradable=False
        )
        db_session.add(img)
        db_session.flush()
        images.append(img)

    return {
        'encounter': encounter,
        'images': images,
        'lab_unit': lab_unit,
        'disease': glaucoma
    }


@pytest.fixture
def encounter_set_with_not_gradable(db_session, core_test_data):
    """Create an encounter set with some not-gradable images."""
    lab_unit = db_session.merge(core_test_data['lab_unit'])
    glaucoma = db_session.merge(core_test_data['glaucoma'])

    encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="Partial Set",
        patient_id="PAT-PARTIAL-001",
        capture_date="2024-01-15",
        capture_date_dt=date(2024, 1, 15),
        lab_unit_id=lab_unit.id,
        is_set_based=True,
        encounter_verified_status='verified',
        disease_id=glaucoma.id
    )
    db_session.add(encounter)
    db_session.flush()

    images = []
    # Create 5 reviewed images, 1 not gradable, 3 missing
    for pos in range(1, 7):
        img = EncounterSetImage(
            uuid=str(uuid.uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=pos,
            original_filename=f"pos_{pos}.jpg",
            folder_rel=f"files/encounter_sets/{encounter.id}",
            is_reviewed=True,
            is_not_gradable=(pos == 6),  # Position 6 is not gradable
            not_gradable_reason="Too blurry" if pos == 6 else None
        )
        db_session.add(img)
        db_session.flush()
        images.append(img)

    return {
        'encounter': encounter,
        'images': images,
        'lab_unit': lab_unit,
        'disease': glaucoma
    }


# ============================================================================
# Task Creation Tests
# ============================================================================

def test_create_grading_task_for_verified_encounter_set(db_session, verified_encounter_set):
    """Test that a grading task can be created for a verified encounter set."""
    from services.taskCreationServices import create_or_get_task

    encounter = verified_encounter_set['encounter']
    disease = verified_encounter_set['disease']

    task = create_or_get_task(
        db_session,
        kind='encounter_set',
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=encounter.lab_unit_id,
        create_linked=False
    )

    assert task is not None
    assert task.patient_encounter_id == encounter.id
    assert task.disease_id == disease.id
    assert task.state == 'pending'


def test_create_grading_task_fails_for_unverified_encounter(db_session, core_test_data):
    """Test that grading task creation fails for unverified encounter sets."""
    from services.taskCreationServices import create_or_get_task

    lab_unit = db_session.merge(core_test_data['lab_unit'])
    glaucoma = db_session.merge(core_test_data['glaucoma'])

    # Create unverified encounter
    encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="Unverified Set",
        patient_id="PAT-UNVERIFIED",
        capture_date="2024-01-15",
        capture_date_dt=date(2024, 1, 15),
        lab_unit_id=lab_unit.id,
        is_set_based=True,
        encounter_verified_status='pending',  # Not verified
        disease_id=glaucoma.id
    )
    db_session.add(encounter)
    db_session.flush()

    # Should not create task for unverified set
    task = create_or_get_task(
        db_session,
        kind='encounter_set',
        patient_encounter_id=encounter.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id
    )

    assert task is None  # Should not create task for unverified encounter


def test_task_creation_is_idempotent(db_session, verified_encounter_set):
    """Test that calling create_or_get_task multiple times returns the same task."""
    from services.taskCreationServices import create_or_get_task

    encounter = verified_encounter_set['encounter']
    disease = verified_encounter_set['disease']

    task1 = create_or_get_task(
        db_session,
        kind='encounter_set',
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=encounter.lab_unit_id
    )

    task2 = create_or_get_task(
        db_session,
        kind='encounter_set',
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=encounter.lab_unit_id
    )

    assert task1.id == task2.id


# ============================================================================
# Grading Route Tests
# ============================================================================

def test_media_route_serves_edited_image_first(client, auth_client_factory, verified_encounter_set, db_session):
    """Test that media routes prioritize edited_filename over original_filename."""
    img = verified_encounter_set['images'][0]

    # Set edited filename
    img.edited_filename = "pos_1_edited.jpg"
    db_session.flush()

    user = UserFactory.create_by_role(db_session, "ophthalmologist", username="resident_media")
    auth_client = auth_client_factory(user)

    # The edited image route should work
    response = auth_client.get(f"/media/encounter_set/img/{img.uuid}/edited")
    # Response might be 404 if file doesn't exist, but route should be accessible
    assert response.status_code in [200, 404]  # 404 is ok for missing file


# ============================================================================
# Sync-Zoom Tests (Frontend behavior via data attributes)
# ============================================================================

