from uuid import uuid4

from models import EncounterSetImage, PatientEncounters, Project
from iitk_api_integration.task_eligibility import (
    IITKTaskEligibilityError,
    apply_iitk_task_eligibility,
    preview_iitk_task_eligibility,
)


def _encounter(db_session, project, *, source_kind="iitk_api", status="pending"):
    encounter = PatientEncounters(
        name="IITK repair test",
        patient_id=f"IITK-{uuid4().hex}",
        capture_date="2026-08-22",
        project_id=project.id,
        is_set_based=True,
        encounter_verified_status=status,
        metadata_json={"upload": {"source_kind": source_kind}},
    )
    db_session.add(encounter)
    db_session.flush()
    return encounter


def _image(db_session, encounter, *, creates_task=False, source_kind="iitk_api"):
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        project_id=encounter.project_id,
        spatial_position=1,
        original_filename="image.jpg",
        folder_rel="files/test",
        asset_kind="clinical_image",
        creates_task=creates_task,
        visible_to_grader=True,
        metadata_json={"source_kind": source_kind},
    )
    db_session.add(image)
    db_session.flush()
    return image


def test_preview_and_apply_are_project_and_source_scoped(db_session):
    target = Project(title="IITK target", code="IITK_TARGET", active=True)
    other = Project(title="IITK other", code="IITK_OTHER", active=True)
    db_session.add_all([target, other])
    db_session.flush()
    target_image = _image(db_session, _encounter(db_session, target))
    non_iitk_image = _image(
        db_session,
        _encounter(db_session, target, source_kind="manual"),
        source_kind="manual",
    )
    other_image = _image(db_session, _encounter(db_session, other))

    preview = preview_iitk_task_eligibility(db_session, project_id=target.id)

    assert preview.images_to_update == 1
    assert preview.encounters_affected == 1
    assert preview.encounter_status_counts == {"pending": 1}
    assert preview.confirmation_token.startswith(f"IITK-TASKS-{target.id}-")

    applied = apply_iitk_task_eligibility(
        db_session,
        project_id=target.id,
        confirmation_token=preview.confirmation_token,
    )
    db_session.refresh(target_image)
    db_session.refresh(non_iitk_image)
    db_session.refresh(other_image)

    assert applied.images_to_update == 1
    assert target_image.creates_task is True
    assert non_iitk_image.creates_task is False
    assert other_image.creates_task is False


def test_apply_rejects_stale_confirmation_token(db_session):
    project = Project(title="IITK token", code="IITK_TOKEN", active=True)
    db_session.add(project)
    db_session.flush()
    image = _image(db_session, _encounter(db_session, project))

    try:
        apply_iitk_task_eligibility(
            db_session,
            project_id=project.id,
            confirmation_token="IITK-TASKS-stale",
        )
    except IITKTaskEligibilityError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("Expected a stale-token error")

    db_session.refresh(image)
    assert image.creates_task is False
