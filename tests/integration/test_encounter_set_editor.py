"""
Tests for Encounter Set Image Editor Integration (Task 3.5 - PII Masking)

TDD approach: Tests written before implementation.

Tests cover:
- Edit route access and permissions
- Save edited image (crop/mask) functionality
- Mark image as anonymized
- Mark all images as anonymized
- Restore original image
- Grading task state validation (block editing if tasks exist)
"""

import pytest
import uuid
import io
import base64
from pathlib import Path
from PIL import Image
from models import (
    ImageMetadata,
    ImagePiiVerification,
    PatientEncounters,
    EncounterSetImage,
    LabUnit,
    GradingTask,
    Disease,
    PiiDetectionJob,
)
from tests.helpers.factories import UserFactory
from datetime import date, datetime

pytestmark = pytest.mark.integration


@pytest.fixture
def encounter_set_with_images(db_session, core_test_data, tmp_path):
    """Create a set-based encounter with multiple images for testing."""
    lab_unit = db_session.merge(core_test_data['lab_unit'])
    glaucoma = db_session.merge(core_test_data['glaucoma'])

    encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="Test Patient Set",
        patient_id="PAT-SET-002",
        capture_date="2023-10-27",
        capture_date_dt=date(2023, 10, 27),
        lab_unit_id=lab_unit.id,
        is_set_based=True,
        encounter_verified_status='pending',
        disease_id=glaucoma.id
    )
    db_session.add(encounter)
    db_session.flush()

    # Create test image files
    images_dir = tmp_path / "files" / "test_sets" / str(encounter.id)
    images_dir.mkdir(parents=True, exist_ok=True)

    images = []
    for pos in range(1, 4):  # Create 3 test images
        img_uuid = str(uuid.uuid4())
        original_filename = f"test_pos_{pos}.jpg"
        edited_filename = f"test_pos_{pos}_edited.jpg"

        # Create dummy image files
        (images_dir / original_filename).write_bytes(b"fake image original data")
        (images_dir / edited_filename).write_bytes(b"fake image edited data")

        image = EncounterSetImage(
            uuid=img_uuid,
            patient_encounter_id=encounter.id,
            spatial_position=pos,
            original_filename=original_filename,
            edited_filename=None,  # Initially no edited version
            thumbnail_filename=f"thumb_{pos}.jpg",
            folder_rel=f"files/test_sets/{encounter.id}",
            is_anonymized=False,
            is_reviewed=False,
            is_not_gradable=False,
            created_at=datetime.now()
        )
        db_session.add(image)
        db_session.flush()
        images.append(image)

    return {
        'encounter': encounter,
        'images': images,
        'lab_unit': lab_unit,
        'disease': glaucoma,
        'tmp_path': tmp_path
    }


def test_edit_encounter_set_image_get_route(client, auth_client_factory, encounter_set_with_images, db_session):
    """Test GET route to edit an encounter set image."""
    user = UserFactory.create_optometrist(db_session, username="opt_edit_access")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    response = auth_client.get(f"/verify_encounter_set/edit/{image.uuid}")

    assert response.status_code == 200
    assert image.uuid.encode() in response.data
    assert b"Edit Image" in response.data


def test_ocr_pii_status_resolves_encounter_set_image(
    auth_client_factory,
    encounter_set_with_images,
    db_session,
    monkeypatch,
):
    """The editor UUID must resolve through the OCR API instead of returning 404."""
    user = UserFactory.create_by_role(
        db_session,
        "optometrist",
        username="opt_ocr_set_image",
        lab_units=[encounter_set_with_images["lab_unit"]],
    )
    auth_client = auth_client_factory(user)
    image = encounter_set_with_images["images"][0]

    monkeypatch.setattr("api.ocr.BASE_DIR", encounter_set_with_images["tmp_path"])

    response = auth_client.get(f"/api/ocr/pii/{image.uuid}")

    assert response.status_code == 200
    assert response.json["success"] is True
    assert response.json["data"]["status"] == "pending"


def test_save_and_restore_encounter_set_edit_uses_effective_paths(
    auth_client_factory,
    encounter_set_with_images,
    db_session,
    csrf_token,
    monkeypatch,
):
    user = UserFactory.create_admin(db_session, username="admin_effective_set_edit")
    auth_client = auth_client_factory(user)
    image = encounter_set_with_images["images"][0]
    root = encounter_set_with_images["tmp_path"]
    folder = root / image.folder_rel
    original_path = folder / image.original_filename
    Image.new("RGB", (80, 60), "white").save(original_path, format="JPEG")
    edited_buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "black").save(edited_buffer, format="JPEG")
    encoded = base64.b64encode(edited_buffer.getvalue()).decode("ascii")
    monkeypatch.setattr("models.BASE_DIR", root)

    save_response = auth_client.post(
        f"/verify_encounter_set/save_edit/{image.uuid}",
        json={
            "image_data": f"data:image/jpeg;base64,{encoded}",
            "allow_graded_edit": False,
        },
        headers={"X-CSRFToken": csrf_token},
    )

    assert save_response.status_code == 200
    db_session.refresh(image)
    edited_path = folder / image.edited_filename
    edited_thumbnail = folder / "thumbnails" / image.thumbnail_filename
    assert edited_path.is_file()
    assert edited_thumbnail.is_file()
    assert db_session.query(ImageMetadata).filter_by(
        image_uuid=image.uuid, image_variant="edited"
    ).one().width == 32
    assert db_session.query(PiiDetectionJob).filter_by(
        image_uuid=image.uuid, image_variant="edited", status="queued"
    ).count() == 1

    db_session.add(ImagePiiVerification(
        image_uuid=image.uuid,
        image_variant="edited",
        pii_status="clear",
        source="auto",
        checked_at=datetime.now(),
    ))
    db_session.commit()

    restore_response = auth_client.post(
        f"/verify_encounter_set/restore_original/{image.uuid}",
        headers={"X-CSRFToken": csrf_token},
    )

    assert restore_response.status_code == 200
    db_session.refresh(image)
    assert image.edited_filename is None
    assert not edited_path.exists()
    assert not edited_thumbnail.exists()
    assert original_path.is_file()
    assert image.thumbnail_filename == f"thm_{image.original_filename}"
    assert (folder / "thumbnails" / image.thumbnail_filename).is_file()
    assert db_session.query(ImageMetadata).filter_by(
        image_uuid=image.uuid, image_variant="edited"
    ).count() == 0
    assert db_session.query(ImagePiiVerification).filter_by(
        image_uuid=image.uuid, image_variant="edited"
    ).count() == 0


def test_edit_encounter_set_image_wrong_role(client, auth_client_factory, encounter_set_with_images, db_session):
    """Test that residents cannot edit encounter set images."""
    user = UserFactory.create_by_role(db_session, "ophthalmologist", username="res_no_edit")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    response = auth_client.get(f"/verify_encounter_set/edit/{image.uuid}")
    assert response.status_code == 403


def test_edit_encounter_set_image_wrong_lab_unit(client, auth_client_factory, encounter_set_with_images, db_session):
    """Test that users cannot edit images from other lab units."""
    # Create user from different lab unit
    other_lab = LabUnit(name="Other Lab", hospital_id=encounter_set_with_images['lab_unit'].hospital_id)
    db_session.add(other_lab)
    db_session.flush()

    user = UserFactory.create_optometrist(db_session, username="opt_other_lab", lab_unit_id=other_lab.id)
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    response = auth_client.get(f"/verify_encounter_set/edit/{image.uuid}")
    assert response.status_code == 403


def test_edit_encounter_set_image_with_grading_task_blocks(client, auth_client_factory, encounter_set_with_images, db_session):
    """Test that editing is blocked when grading tasks exist for the encounter."""
    user = UserFactory.create_optometrist(db_session, username="opt_with_task")
    auth_client = auth_client_factory(user)

    encounter = encounter_set_with_images['encounter']
    image = encounter_set_with_images['images'][0]

    # Create a grading task for the encounter
    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=encounter_set_with_images['disease'].id,
        lab_unit_id=encounter.lab_unit_id,
        state='pending',
        created_by_id=user.id
    )
    db_session.add(task)
    db_session.flush()

    response = auth_client.get(f"/verify_encounter_set/edit/{image.uuid}", follow_redirects=True)

    # Should redirect with error message
    assert response.status_code == 200
    assert b"Editing blocked" in response.data or b"blocked" in response.data.lower()


def test_save_edited_encounter_set_image(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token, tmp_path):
    """Test saving an edited (cropped/masked) image."""
    user = UserFactory.create_optometrist(db_session, username="opt_save_edit")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    # Simulate sending edited image data (coordinates for crop/mask)
    edit_data = {
        'x': 10,
        'y': 10,
        'width': 200,
        'height': 200,
        'rotation': 0
    }

    # In real scenario, this would send actual image data
    # For test, we verify the route exists and accepts the data
    response = auth_client.post(
        f"/verify_encounter_set/save_edit/{image.uuid}",
        json=edit_data,
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200
    assert response.json['success'] is True

    # Verify edited_filename was set
    db_session.refresh(image)
    assert image.edited_filename is not None
    assert '_edited' in image.edited_filename


def test_mark_image_as_anonymized(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test marking a single image as anonymized."""
    user = UserFactory.create_optometrist(db_session, username="opt_mark_anon")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    response = auth_client.post(
        f"/verify_encounter_set/mark_anonymized/{image.uuid}",
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200
    assert response.json['success'] is True

    # Verify is_anonymized flag was set
    db_session.refresh(image)
    assert image.is_anonymized is True


def test_mark_all_images_as_anonymized(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test marking all images in an encounter set as anonymized."""
    user = UserFactory.create_optometrist(db_session, username="opt_mark_all")
    auth_client = auth_client_factory(user)

    encounter = encounter_set_with_images['encounter']
    images = encounter_set_with_images['images']

    # Initially none are anonymized
    for img in images:
        assert img.is_anonymized is False

    response = auth_client.post(
        f"/verify_encounter_set/mark_all_anonymized/{encounter.uuid}",
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200
    assert response.json['success'] is True

    # Verify all images are marked as anonymized
    for img in images:
        db_session.refresh(img)
        assert img.is_anonymized is True


def test_restore_original_encounter_set_image(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token, tmp_path):
    """Test restoring the original image (removing edited version)."""
    user = UserFactory.create_optometrist(db_session, username="opt_restore")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    # First, set an edited filename
    image.edited_filename = f"test_pos_1_edited.jpg"
    db_session.flush()

    # Verify edited file exists
    images_dir = encounter_set_with_images['tmp_path'] / "files" / "test_sets" / str(encounter_set_with_images['encounter'].id)
    edited_file = images_dir / image.edited_filename
    edited_file.write_bytes(b"edited data")

    response = auth_client.post(
        f"/verify_encounter_set/restore_original/{image.uuid}",
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200
    assert response.json['success'] is True

    # Verify edited_filename was cleared
    db_session.refresh(image)
    assert image.edited_filename is None


def test_restore_original_with_grading_task_blocks(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test that restoring original is blocked when grading tasks exist."""
    user = UserFactory.create_optometrist(db_session, username="opt_restore_block")
    auth_client = auth_client_factory(user)

    encounter = encounter_set_with_images['encounter']
    image = encounter_set_with_images['images'][0]

    # Set edited filename
    image.edited_filename = "edited.jpg"
    db_session.flush()

    # Create a grading task
    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=encounter_set_with_images['disease'].id,
        lab_unit_id=encounter.lab_unit_id,
        state='in_progress',
        created_by_id=user.id
    )
    db_session.add(task)
    db_session.flush()

    response = auth_client.post(
        f"/verify_encounter_set/restore_original/{image.uuid}",
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 409  # Conflict
    assert b"blocked" in response.data.lower() or b"progress" in response.data.lower()


def test_edit_page_loads_edited_version_when_exists(client, auth_client_factory, encounter_set_with_images, db_session, tmp_path):
    """Test that the edit page loads the edited version if it exists."""
    user = UserFactory.create_optometrist(db_session, username="opt_edit_version")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]
    encounter = encounter_set_with_images['encounter']

    # Create edited file
    image.edited_filename = "test_pos_1_edited.jpg"
    db_session.flush()

    images_dir = encounter_set_with_images['tmp_path'] / "files" / "test_sets" / str(encounter.id)
    edited_file = images_dir / image.edited_filename
    edited_file.write_bytes(b"edited version data")

    response = auth_client.get(f"/verify_encounter_set/edit/{image.uuid}")

    assert response.status_code == 200
    # Should load edited version in the editor
    assert image.edited_filename.encode() in response.data or b"edited" in response.data.lower()


def test_verification_page_shows_anonymization_status(client, auth_client_factory, encounter_set_with_images, db_session):
    """Test that the verification page shows which images have been anonymized."""
    user = UserFactory.create_optometrist(db_session, username="opt_anon_status")
    auth_client = auth_client_factory(user)

    encounter = encounter_set_with_images['encounter']
    image = encounter_set_with_images['images'][0]

    # Mark first image as anonymized
    image.is_anonymized = True
    db_session.flush()

    response = auth_client.get(f"/verify_encounter_set/verify/{encounter.uuid}")

    assert response.status_code == 200
    # Should show anonymization indicator
    assert b"anonymiz" in response.data.lower() or b"mask" in response.data.lower()


def test_finalize_verification_requires_all_images_reviewed(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test that finalizing verification requires all images to be reviewed (edited or marked as not gradable)."""
    user = UserFactory.create_optometrist(db_session, username="opt_finalize_check")
    auth_client = auth_client_factory(user)

    encounter = encounter_set_with_images['encounter']

    # Not all images are reviewed
    for img in encounter_set_with_images['images']:
        assert img.is_reviewed is False

    response = auth_client.post(
        f"/verify_encounter_set/finalize/{encounter.uuid}",
        headers={'X-CSRFToken': csrf_token},
        follow_redirects=True
    )

    # Should warn about unreviewed images
    assert response.status_code == 200
    assert b"review" in response.data.lower() or b"all images" in response.data.lower()


def test_mark_image_as_not_gradable(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test marking a single image as not gradable (e.g., poor quality, missing)."""
    user = UserFactory.create_optometrist(db_session, username="opt_not_gradable")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]
    reason = "Blurry image - cannot assess optic nerve head"

    response = auth_client.post(
        f"/verify_encounter_set/mark_not_gradable/{image.uuid}",
        json={'reason': reason},
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200
    assert response.json['success'] is True

    # Verify image was marked as not gradable
    db_session.refresh(image)
    assert image.is_not_gradable is True
    assert image.not_gradable_reason == reason


def test_mark_image_as_not_gradable_counts_as_reviewed(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test that marking an image as not gradable also marks it as reviewed."""
    user = UserFactory.create_optometrist(db_session, username="opt_not_gradable_reviewed")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    response = auth_client.post(
        f"/verify_encounter_set/mark_not_gradable/{image.uuid}",
        json={'reason': 'Too dark'},
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200

    db_session.refresh(image)
    # Should be marked as reviewed even though it's not gradable
    assert image.is_reviewed is True


def test_mark_image_as_not_gradable_with_empty_reason(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test that marking not gradable requires a reason."""
    user = UserFactory.create_optometrist(db_session, username="opt_no_reason")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    response = auth_client.post(
        f"/verify_encounter_set/mark_not_gradable/{image.uuid}",
        json={'reason': ''},
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 400
    assert b"reason" in response.data.lower() or b"required" in response.data.lower()


def test_undo_not_gradable_status(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test undoing the not gradable status for an image."""
    user = UserFactory.create_optometrist(db_session, username="opt_undo_not_gradable")
    auth_client = auth_client_factory(user)

    image = encounter_set_with_images['images'][0]

    # First mark as not gradable
    image.is_not_gradable = True
    image.not_gradable_reason = "Blurry"
    image.is_reviewed = True
    db_session.flush()

    # Now undo
    response = auth_client.post(
        f"/verify_encounter_set/undo_not_gradable/{image.uuid}",
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200
    assert response.json['success'] is True

    db_session.refresh(image)
    assert image.is_not_gradable is False
    assert image.not_gradable_reason is None
    # is_reviewed should remain True since it was reviewed


def test_finalize_with_all_images_reviewed_succeeds(client, auth_client_factory, encounter_set_with_images, db_session, csrf_token):
    """Test that finalization succeeds when all images are reviewed."""
    user = UserFactory.create_optometrist(db_session, username="opt_finalize_success")
    auth_client = auth_client_factory(user)

    encounter = encounter_set_with_images['encounter']

    # Mark all images as reviewed
    for img in encounter_set_with_images['images']:
        img.is_reviewed = True
        db_session.flush()

    response = auth_client.post(
        f"/verify_encounter_set/finalize/{encounter.uuid}",
        headers={'X-CSRFToken': csrf_token},
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b"verified successfully" in response.data.lower()

    db_session.refresh(encounter)
    assert encounter.encounter_verified_status == 'verified'
