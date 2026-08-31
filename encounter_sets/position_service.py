"""Atomic, resource-scoped EncounterSet image position changes."""

from sqlalchemy import select

from authz.behaviors import role_scoped_rows
from authz.context import access_context
from models import EncounterSetImage, PatientEncounters
from services.uploads.access import encounter_columns
from verify_encounter_set.reopen_service import check_reopen_guard


class PositionMutationError(ValueError):
    status_code = 400


class PositionMutationNotFound(PositionMutationError):
    status_code = 404


class PositionMutationConflict(PositionMutationError):
    status_code = 409


def move_encounter_set_image(db, *, user, image_uuid: str, new_position: int) -> None:
    """Move or swap one image after locking and rechecking every invariant."""
    if type(new_position) is not int or new_position < 1:
        raise PositionMutationError("Position must be a positive integer.")
    image = db.execute(
        select(EncounterSetImage)
        .where(EncounterSetImage.uuid == image_uuid)
        .with_for_update()
    ).scalar_one_or_none()
    if image is None:
        raise PositionMutationNotFound("Image not found.")
    encounter_query = select(PatientEncounters).where(
        PatientEncounters.id == image.patient_encounter_id,
        PatientEncounters.is_set_based.is_(True),
    ).with_for_update()
    encounter_query = role_scoped_rows(
        encounter_query,
        access_context(db, user),
        encounter_columns(PatientEncounters),
        lab_roles={"verifier"},
        project_roles={"verifier"},
        allow_admin=True,
    )
    encounter = db.execute(encounter_query).scalar_one_or_none()
    if encounter is None:
        raise PositionMutationNotFound("Image not found.")
    if encounter.encounter_verified_status not in {None, "pending"}:
        raise PositionMutationConflict("Image positions are locked after verification.")
    if check_reopen_guard(db, encounter):
        raise PositionMutationConflict("Image positions are locked after grading starts.")

    images = db.execute(
        select(EncounterSetImage)
        .where(EncounterSetImage.patient_encounter_id == encounter.id)
        .order_by(EncounterSetImage.id)
        .with_for_update()
    ).scalars().all()
    occupied = next(
        (row for row in images if row.spatial_position == new_position and row.id != image.id),
        None,
    )
    if occupied is None or image.spatial_position == new_position:
        image.spatial_position = new_position
        db.flush()
        return

    old_position = image.spatial_position
    temporary_position = max(row.spatial_position for row in images) + 1
    image.spatial_position = temporary_position
    db.flush()
    occupied.spatial_position = old_position
    db.flush()
    image.spatial_position = new_position
    db.flush()
