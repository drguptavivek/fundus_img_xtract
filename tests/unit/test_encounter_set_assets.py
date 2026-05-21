import pytest

from encounter_sets.assets import (
    ASSET_KIND_CLINICAL_IMAGE,
    ASSET_KIND_DOCUMENT_IMAGE,
    list_clinical_task_images,
    normalize_supporting_asset_kind,
)
from encounter_sets.models import EncounterSetAttachment
from models import EncounterSetImage, PatientEncounters


def _encounter(db_session):
    encounter = PatientEncounters(
        is_set_based=True,
        name="Asset Test Patient",
        patient_id="ASSET123",
        capture_date="2026-05-21",
    )
    db_session.add(encounter)
    db_session.flush()
    return encounter


def test_encounter_set_image_defaults_to_clinical_task_evidence(db_session):
    encounter = _encounter(db_session)
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="clinical.jpg",
        folder_rel="files/encounter_sets/test",
    )
    db_session.add(image)
    db_session.flush()

    assert image.asset_kind == ASSET_KIND_CLINICAL_IMAGE
    assert image.creates_task is True
    assert image.is_pii is False
    assert image.visible_to_grader is True


def test_supporting_document_image_attachment_never_creates_tasks(db_session):
    encounter = _encounter(db_session)
    attachment = EncounterSetAttachment(
        patient_encounter_id=encounter.id,
        asset_kind=ASSET_KIND_DOCUMENT_IMAGE,
        original_filename="referral-slip.jpg",
        stored_filename="attachment.jpg",
        folder_rel="files/encounter_sets/test",
        mime_type="image/jpeg",
    )
    db_session.add(attachment)
    db_session.flush()

    assert attachment.is_pii is True
    assert attachment.visible_to_grader is False
    assert attachment.creates_task is False


def test_clinical_task_image_query_excludes_non_task_images(db_session):
    encounter = _encounter(db_session)
    included = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="included.jpg",
        folder_rel="files/encounter_sets/test",
    )
    excluded = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=2,
        original_filename="excluded.jpg",
        folder_rel="files/encounter_sets/test",
        creates_task=False,
    )
    db_session.add_all([included, excluded])
    db_session.flush()

    assert list_clinical_task_images(db_session, encounter.id) == [included]


def test_normalize_supporting_asset_kind_rejects_clinical_image():
    with pytest.raises(ValueError):
        normalize_supporting_asset_kind(ASSET_KIND_CLINICAL_IMAGE)
