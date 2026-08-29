from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select

from models import DirectImageUpload, Disease, Hospital, LabUnit, User
from upload_profiles.service import (
    UploadProfileError,
    UploadSelection,
    validate_pregraded_upload_scope,
)

from .dtos import AuthorizedGradeImport, AuthorizedGradeTarget, PregradedImageSelection
from .errors import denied, invalid


def require_pregraded_uploader(*, actor: User) -> None:
    """Dedicated qualification only; admin is the sole break-glass role."""
    if not actor.is_active or not actor.has_role("pregarded_uploader", "admin"):
        raise denied("The dedicated pregraded-uploader role is required.")


def authorize_image_upload(db, *, actor: User, selection: PregradedImageSelection):
    """Validate role, lineage, and the exact assigned pregraded profile."""
    require_pregraded_uploader(actor=actor)
    hospital = db.get(Hospital, selection.hospital_id)
    lab_unit = db.get(LabUnit, selection.lab_unit_id)
    if hospital is None or lab_unit is None:
        raise invalid("The selected Hospital or Lab Unit does not exist.")
    if lab_unit.hospital_id != hospital.id:
        raise invalid("The selected Lab Unit does not belong to the selected Hospital.")
    if db.get(Disease, selection.disease_id) is None:
        raise invalid("The selected disease does not exist.")
    try:
        return validate_pregraded_upload_scope(
            db,
            actor.id,
            UploadSelection(
                project_id=selection.project_id,
                lab_unit_id=selection.lab_unit_id,
                disease_id=selection.disease_id,
                camera_id=selection.camera_id,
                area_id=selection.area_id,
                is_mydriatic=selection.is_mydriatic,
                profile_id=selection.profile_id,
            ),
        )
    except UploadProfileError as exc:
        raise denied(exc.message) from exc


def authorize_grade_import_targets(
    db,
    *,
    actor: User,
    hospital_id: int,
    lab_unit_id: int,
    disease_id: int,
    image_names: Iterable[str],
) -> AuthorizedGradeImport:
    """Resolve workbook targets from stored records and authorize every target."""
    require_pregraded_uploader(actor=actor)
    hospital = db.get(Hospital, hospital_id)
    lab_unit = db.get(LabUnit, lab_unit_id)
    disease = db.get(Disease, disease_id)
    if hospital is None or lab_unit is None or disease is None:
        raise invalid("The supplied Hospital, Lab Unit, or disease does not exist.")
    if lab_unit.hospital_id != hospital.id:
        raise invalid("The supplied Lab Unit does not belong to the supplied Hospital.")

    raw_names = tuple(image_names)
    if any(not name or not name.strip() for name in raw_names):
        raise invalid("The workbook contains a blank image target; import denied.")
    supplied_names = tuple(name.strip().lower() for name in raw_names)
    normalized_names = tuple(dict.fromkeys(supplied_names))
    if not normalized_names:
        raise invalid("The workbook contains no image targets.")
    if len(normalized_names) != len(supplied_names):
        raise invalid("The workbook contains duplicate image targets; import denied.")
    rows = db.execute(
        select(DirectImageUpload).where(
            func.lower(DirectImageUpload.original_filename).in_(normalized_names),
            DirectImageUpload.hospital_id == hospital_id,
            DirectImageUpload.lab_unit_id == lab_unit_id,
            DirectImageUpload.disease_id == disease_id,
            DirectImageUpload.is_pregraded.is_(True),
        ).with_for_update()
    ).scalars().all()
    by_name: dict[str, list[DirectImageUpload]] = {}
    for row in rows:
        by_name.setdefault((row.original_filename or "").strip().lower(), []).append(row)
    for name in normalized_names:
        matches = by_name.get(name, [])
        if not matches:
            raise invalid(f"No pregraded image matches workbook target '{name}'.")
        if len(matches) != 1:
            raise invalid(f"Workbook target '{name}' is ambiguous; import denied.")

    profiles = []
    uploads = [by_name[name][0] for name in normalized_names]
    for upload in uploads:
        if upload.project_id is None:
            raise invalid("A target image has no project lineage; import denied.")
        profiles.append(
            authorize_image_upload(
                db,
                actor=actor,
                selection=PregradedImageSelection(
                    project_id=upload.project_id,
                    hospital_id=upload.hospital_id,
                    lab_unit_id=upload.lab_unit_id,
                    disease_id=upload.disease_id,
                    camera_id=upload.camera_id,
                    area_id=upload.area_id,
                    is_mydriatic=upload.is_mydriatic,
                ),
            )
        )
    project_ids = {upload.project_id for upload in uploads}
    if len(project_ids) != 1:
        raise invalid("One workbook may not span multiple projects.")
    return AuthorizedGradeImport(
        project_id=next(iter(project_ids)),
        lab_unit_id=lab_unit_id,
        disease_id=disease_id,
        upload_ids=tuple(upload.id for upload in uploads),
        profile_ids=tuple(sorted({profile.profile_id for profile in profiles})),
        targets=tuple(
            AuthorizedGradeTarget(
                normalized_image_name=(upload.original_filename or "").strip().lower(),
                upload_id=upload.id,
            )
            for upload in uploads
        ),
    )
