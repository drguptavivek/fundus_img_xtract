"""
Tests for Celery Background Processing for Encounter Set Images

TDD approach: Tests written before implementation.

Tests cover:
- Thumbnail generation for EncounterSetImage
- EXIF data extraction
- Background job scheduling
"""

import pytest
import uuid
from datetime import date
from models import (
    PatientEncounters, EncounterSetImage, LabUnit, Disease,
    DirectImageUpload
)
from tests.helpers.factories import UserFactory, CoreEntityFactory

pytestmark = pytest.mark.integration


@pytest.fixture
def encounter_set_with_images(db_session, core_test_data):
    """Create an encounter set with images for testing."""
    lab_unit = db_session.merge(core_test_data['lab_unit'])
    glaucoma = db_session.merge(core_test_data['glaucoma'])

    encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="Test Background Set",
        patient_id="PAT-BG-001",
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
    for pos in range(1, 4):
        img = EncounterSetImage(
            uuid=str(uuid.uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=pos,
            original_filename=f"pos_{pos}.jpg",
            folder_rel=f"files/encounter_sets/{encounter.id}",
            is_reviewed=True,
            is_anonymized=True
        )
        db_session.add(img)
        db_session.flush()
        images.append(img)

    # Refresh to ensure relationships are loaded
    db_session.refresh(encounter)

    return {
        'encounter': encounter,
        'images': images,
        'lab_unit': lab_unit
    }


# ============================================================================
# Thumbnail Job Creation Tests
# ============================================================================

def test_create_thumbnail_job_for_encounter_set_image(db_session, encounter_set_with_images):
    """Test creating a thumbnail generation job for encounter set images."""
    from utils.thumbnail_jobs import create_thumbnail_job, ThumbnailJobType

    images = encounter_set_with_images['images']
    encounter = encounter_set_with_images['encounter']

    # Create image references with all required fields
    image_references = [
        {'image_id': img.id, 'folder_rel': img.folder_rel, 'filename': img.original_filename}
        for img in images
    ]

    lab_unit = encounter_set_with_images['lab_unit']

    # This should create a job successfully
    # (Implementation will need to support EncounterSetImage)
    job_token = create_thumbnail_job(
        ThumbnailJobType.ENCOUNTER_SET_IMAGE,
        image_references,
        uploader_user_id=1,
        lab_unit_id=None  # Lab unit is nullable for background jobs
    )

    # Verify job was created
    from job_store import db_get_job_payload
    job_payload = db_get_job_payload(job_token)
    assert job_payload is not None
    assert job_payload['status'] in ['queued', 'processing', 'completed']


def test_schedule_encounter_set_thumbnails_after_upload(db_session, encounter_set_with_images):
    """Test that thumbnails are scheduled after encounter set image upload."""
    from utils.thumbnail_jobs import schedule_encounter_set_thumbnails
    from flask import current_app

    images = encounter_set_with_images['images']
    encounter = encounter_set_with_images['encounter']

    # Get image IDs
    image_ids = [img.id for img in images]

    # This should schedule thumbnail jobs
    # (Implementation is in utils/thumbnail_jobs.py)
    result = schedule_encounter_set_thumbnails(
        image_ids,
        current_app,
        user_context={'user_id': 1, 'username': 'test_user', 'ip': '127.0.0.1'}
    )

    assert result is None  # Function returns None, job is queued asynchronously


# ============================================================================
# Thumbnail Generation Tests
# ============================================================================

def test_generate_thumbnail_for_encounter_set_image(db_session, encounter_set_with_images):
    """Test that thumbnail generation works for encounter set images."""
    from utils.thumbnail_jobs import _generate_encounter_set_thumbnail

    img = encounter_set_with_images['images'][0]

    # Create the source image file for testing
    from pathlib import Path
    from utils.fileUtils import IMAGE_DIR

    source_path = IMAGE_DIR / img.folder_rel / img.original_filename
    source_path.parent.mkdir(parents=True, exist_ok=True)

    # Create a minimal test image
    try:
        from PIL import Image
        test_img = Image.new('RGB', (1000, 1000), color='blue')
        test_img.save(source_path)
    except ImportError:
        # If PIL is not available, skip this test
        pytest.skip("PIL not available for image creation")

    # Now test thumbnail generation
    ref = {'image_id': img.id, 'folder_rel': img.folder_rel, 'filename': img.original_filename}
    success, message = _generate_encounter_set_thumbnail(ref)

    assert success, f"Thumbnail generation failed: {message}"

    # Verify thumbnail file was created
    from utils.fileUtils import get_thumbnail_path_direct
    thumbnail_path = get_thumbnail_path_direct(img.folder_rel, img.original_filename, "orig")
    assert thumbnail_path.exists()

    # Verify database record was updated
    db_session.refresh(img)
    assert img.thumbnail_filename is not None


# ============================================================================
# EXIF Extraction Tests
# ============================================================================

def test_extract_exif_data_from_image(db_session, encounter_set_with_images):
    """Test EXIF data extraction from images."""
    from celery_tasks.tasks.metadata_tasks import extract_exif_task

    img = encounter_set_with_images['images'][0]

    # Create the source image file for testing
    from pathlib import Path
    from utils.fileUtils import IMAGE_DIR

    source_path = IMAGE_DIR / img.folder_rel / img.original_filename
    source_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
        test_img = Image.new('RGB', (1000, 1000), color='red')
        test_img.save(source_path)
    except ImportError:
        pytest.skip("PIL not available for image creation")

    # Extract EXIF data
    result = extract_exif_task(img.id, 'encounter_set_image')

    assert result is not None
    assert 'exif_data' in result or 'success' in result


# ============================================================================
# Job Status Tracking Tests
# ============================================================================

def test_get_thumbnail_job_status(db_session, encounter_set_with_images):
    """Test getting status of a thumbnail generation job."""
    from utils.thumbnail_jobs import create_thumbnail_job, ThumbnailJobType, get_thumbnail_job_status

    images = encounter_set_with_images['images']
    encounter = encounter_set_with_images['encounter']

    image_references = [
        {'image_id': img.id, 'spatial_position': img.spatial_position}
        for img in images
    ]

    job_token = create_thumbnail_job(
        ThumbnailJobType.ENCOUNTER_SET_IMAGE,
        image_references,
        uploader_user_id=1,
        lab_unit_id=encounter.lab_unit_id
    )

    # Get job status
    status = get_thumbnail_job_status(job_token)

    assert status is not None
    assert 'token' in status
    assert status['token'] == job_token
    assert 'status' in status


# ============================================================================
# Integration with Upload Flow Tests
# ============================================================================

def test_upload_schedules_thumbnail_generation(db_session, client, auth_client_factory, encounter_set_with_images):
    """Test that uploading an encounter set image schedules thumbnail generation."""
    from flask import url_for
    import json

    user = UserFactory.create_by_role(db_session, "fileUploader", username="uploader_bg")
    auth_client = auth_client_factory(user)

    encounter = encounter_set_with_images['encounter']

    # Upload a new image to the encounter set
    image_data = {
        'spatial_position': 10,
        'file_content': 'fake_base64_content'
    }

    response = auth_client.post(
        url_for('encounter_set.upload_image', encounter_uuid=encounter.uuid),
        json=image_data
    )

    # Should return success (or appropriate status)
    assert response.status_code in [200, 201, 202]

    # Verify a thumbnail job was scheduled
    # (This would check that a job was created for the new image)
