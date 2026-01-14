"""
Test AdHocTaskCreation model and its relationship to GradingTask.

Tests verify:
1. AdHocTaskCreation can be persisted with valid user reference
2. GradingTask.ad_hoc_id can be set to link back to AdHocTaskCreation
3. The check constraint requiring either encounter_file_id or direct_image_upload_id is satisfied
"""
import json
from datetime import timezone

from models import AdHocTaskCreation, GradingTask, User, Disease, LabUnit, Hospital, Camera, Area
from tests.helpers.test_factories import TestDataFactory


def test_ad_hoc_batch_persist_and_link(db_session):
    """
    Test AdHocTaskCreation persistence and GradingTask linkage.

    Verifies that:
    - AdHocTaskCreation can be created with valid user ID
    - GradingTask can reference the batch via ad_hoc_id
    - Database constraints are satisfied
    """
    # Get required entities from seeded database
    user = db_session.query(User).first()
    disease = db_session.query(Disease).first()
    lab_unit = db_session.query(LabUnit).first()
    hospital = db_session.query(Hospital).first()
    camera = db_session.query(Camera).first()
    area = db_session.query(Area).first()

    assert user is not None, "No users found - ensure seed_database fixture runs"
    assert disease is not None, "No diseases found - ensure seed_database fixture runs"
    assert lab_unit is not None, "No lab units found - ensure seed_database fixture runs"
    assert hospital is not None, "No hospitals found - ensure seed_database fixture runs"
    assert camera is not None, "No cameras found - ensure seed_database fixture runs"
    assert area is not None, "No areas found - ensure seed_database fixture runs"

    # Step 1: Create AdHocTaskCreation batch
    batch = AdHocTaskCreation(
        created_by_id=user.id,
        diseases_json=json.dumps([disease.id]),
        max_images=5,
        filters_json=json.dumps({'source': 'direct'}),
        selected_image_refs_json=json.dumps([]),
    )
    db_session.add(batch)
    db_session.flush()

    # Step 2: Create a DirectImageUpload (required by GradingTask check constraint)
    direct_upload = TestDataFactory.create_direct_image_upload(
        db_session,
        lab_unit_id=lab_unit.id,
        uploader_id=user.id,
        hospital_id=hospital.id,
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
        filename="test_adhoc_image.jpg",
    )

    # Step 3: Create GradingTask linked to both DirectImageUpload and AdHocTaskCreation
    gt = GradingTask(
        disease_id=disease.id,
        lab_unit_id=lab_unit.id,
        state='pending',
        direct_image_upload_id=direct_upload.id,  # Satisfies check constraint
        ad_hoc_id=batch.id,  # Links to AdHocTaskCreation for audit trail
    )
    db_session.add(gt)
    db_session.commit()

    # Verify
    assert batch.id is not None
    assert gt.ad_hoc_id == batch.id
    assert gt.direct_image_upload_id == direct_upload.id
    assert gt.encounter_file_id is None  # Exactly one must be set
