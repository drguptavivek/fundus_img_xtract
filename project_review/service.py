"""Scoped, non-PII read model for project summary, uploads, and gradings."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, exists, func, literal, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from iitk_api_integration.models import IITKApiProjectConfig
from models import (
    DirectImageUpload,
    DirectImageVerify,
    ImagePiiVerification,
    Disease,
    DiabeticRetinopathyReport,
    AMDReport,
    GlaucomaReport,
    AIInferenceRun,
    AIModelIntegration,
    EncounterFile,
    EncounterSetGradingPackage,
    EncounterSetGradingScope,
    EncounterSetImage,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
    Project,
    Role,
    User,
)
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
)
from project_configuration.service import configured_project_lab_unit_ids

from .dto import (
    ProjectChoiceDTO,
    ProjectGradingDTO,
    ProjectGradingsDTO,
    ProjectMetricDTO,
    ProjectLabUnitChoiceDTO,
    ProjectProfileDTO,
    ProjectScopeDTO,
    ProjectSummaryDTO,
    ProjectUploadDTO,
    ProjectUploadPageDTO,
    DirectImageVerificationDTO,
)
from .exceptions import ProjectReviewNotFound
from .configuration import effective_configuration
from authz.project_access import (
    allowed_project_lab_unit_ids,
    can_manage_project_access,
    can_manage_project_uploaders,
    can_verify_direct_images,
)
from authz.project_roles import PROJECT_ASSIGNABLE_ROLES


@dataclass(frozen=True)
class _ResolvedScope:
    project_wide: bool
    hospital_ids: frozenset[int]
    lab_unit_ids: frozenset[int]


def list_projects(db: Session, *, user: User) -> tuple[ProjectChoiceDTO, ...]:
    statement = select(Project).order_by(Project.active.desc(), Project.title)
    if not user.has_role("admin"):
        role_membership = exists().where(
            ProjectRoleGrant.project_id == Project.id,
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            ProjectRoleGrant.role_id == Role.id,
            Role.name.in_(PROJECT_ASSIGNABLE_ROLES),
        )
        statement = statement.where(role_membership)
    return tuple(_project_dto(row) for row in db.execute(statement).scalars())


def get_summary(db: Session, *, user: User, project_id: int) -> ProjectSummaryDTO:
    project, scope = _project_and_scope(db, user=user, project_id=project_id)
    encounter_scope = _encounter_scope_clause(scope)
    direct_scope = _direct_scope_clause(scope)

    encounter_count = _scalar_count(db, select(func.count(PatientEncounters.id)).where(
        PatientEncounters.project_id == project.id,
        PatientEncounters.is_set_based.is_(True),
        encounter_scope,
    ))
    verified_encounter_count, project_encounter_count = db.execute(select(
        func.count(PatientEncounters.id).filter(
            PatientEncounters.encounter_verified_status == "verified"
        ),
        func.count(PatientEncounters.id),
    ).where(
        PatientEncounters.project_id == project.id,
        encounter_scope,
    )).one()
    verified_encounter_count = int(verified_encounter_count or 0)
    project_encounter_count = int(project_encounter_count or 0)
    verified_encounter_percent = (
        round(verified_encounter_count / project_encounter_count * 100)
        if project_encounter_count else 0
    )
    set_image_count = _scalar_count(db, select(func.count(EncounterSetImage.id)).join(
        PatientEncounters, PatientEncounters.id == EncounterSetImage.patient_encounter_id
    ).where(
        PatientEncounters.project_id == project.id,
        encounter_scope,
        or_(
            EncounterSetImage.metadata_json["source_present"].as_boolean().is_(None),
            EncounterSetImage.metadata_json["source_present"].as_boolean().is_(True),
        ),
    ))
    direct_count = _scalar_count(db, select(func.count(DirectImageUpload.id)).where(
        DirectImageUpload.project_id == project.id, direct_scope
    ))
    pregraded_count = _scalar_count(db, select(func.count(DirectImageUpload.id)).where(
        DirectImageUpload.project_id == project.id,
        DirectImageUpload.is_pregraded.is_(True),
        direct_scope,
    ))
    package_count = _scalar_count(db, select(func.count(EncounterSetGradingPackage.id)).join(
        PatientEncounters,
        PatientEncounters.id == EncounterSetGradingPackage.patient_encounter_id,
    ).where(PatientEncounters.project_id == project.id, encounter_scope))
    package_help = "Each workflow is created for one EncounterSet from a configured grading package and contains one or more grading tasks."
    grading_rows = _grading_rows(db, project.id, scope, top_level_only=True)
    task_count = sum(row.task_count for row in grading_rows)
    finalised_count = sum(row.final_count for row in grading_rows)
    grading_stage_metrics = (
        ProjectMetricDTO("first_grading", "Need G-1", sum(row.first_grading_count for row in grading_rows)),
        ProjectMetricDTO("second_grading", "Need G-2", sum(row.second_grading_count for row in grading_rows)),
        ProjectMetricDTO("adjudication", "Need Adjudication", sum(row.adjudication_count for row in grading_rows)),
        ProjectMetricDTO("final", "Complete", finalised_count),
    )
    allowed_labs = _allowed_lab_ids(db, scope)
    configuration = effective_configuration(
        db,
        project_id=project.id,
        allowed_lab_ids=allowed_labs,
        include_people=can_manage_project_access(
            db, user, project_id=project.id
        ),
    )
    metrics = [
        ProjectMetricDTO("encounter_sets", "EncounterSets", encounter_count),
        ProjectMetricDTO(
            "encounters_verified_percent",
            "% Encounters Verified",
            verified_encounter_percent,
            f"{verified_encounter_count:,} of {project_encounter_count:,} in-scope project encounters are verified.",
            "%",
        ),
        ProjectMetricDTO("single_uploads", "Single-image uploads", direct_count),
        ProjectMetricDTO("total_images", "Total images", set_image_count + direct_count),
        ProjectMetricDTO("pregraded_images", "Pre-graded images", pregraded_count),
        ProjectMetricDTO("grading_packages", "EncounterSet grading workflows", package_count, package_help),
        ProjectMetricDTO("grading_tasks", "Top-level grading tasks", task_count),
    ]
    if any(source.name == "Remidio API" for source in configuration["sources"]):
        report_counts = {
            "dr": _report_count(db, DiabeticRetinopathyReport, project.id, encounter_scope),
            "amd": _report_count(db, AMDReport, project.id, encounter_scope),
            "glaucoma": _report_count(db, GlaucomaReport, project.id, encounter_scope),
        }
        metrics.extend([
            ProjectMetricDTO("remidio_dr_reports", "Remidio DR reports", report_counts["dr"]),
            ProjectMetricDTO("remidio_amd_reports", "Remidio AMD reports", report_counts["amd"]),
            ProjectMetricDTO("remidio_glaucoma_reports", "Remidio glaucoma reports", report_counts["glaucoma"]),
        ])
    if any(
        analysis.provider == "wadhwani_glaucoma"
        for analysis in configuration["automated_analyses"]
    ):
        metrics.append(ProjectMetricDTO(
            "wadhwani_inferences", "Wadhwani glaucoma inferences",
            _wadhwani_count(db, project.id, scope),
        ))
    return ProjectSummaryDTO(
        project=_project_dto(project),
        scope=_scope_dto(db, scope),
        metrics=tuple(metrics),
        profiles=_profile_configuration(db, project.id),
        grading_rows=grading_rows,
        grading_stage_metrics=grading_stage_metrics,
        grading_completion_percent=round((finalised_count / task_count) * 100) if task_count else 0,
        **configuration,
    )


def get_uploads(
    db: Session,
    *,
    user: User,
    project_id: int,
    page: int = 1,
    per_page: int = 100,
    status: str = "all",
    lab_unit_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ProjectUploadPageDTO:
    project, scope = _project_and_scope(db, user=user, project_id=project_id)
    page = max(1, page)
    per_page = min(200, max(1, per_page))
    rows, total_rows, source_counts = _upload_rows(
        db, project.id, scope, page=page, per_page=per_page,
        status=status, lab_unit_id=lab_unit_id, date_from=date_from, date_to=date_to,
        verifier_lab_unit_ids=allowed_project_lab_unit_ids(
            db, user, project_id=project.id, roles={"verifier", "project_admin"}
        ),
    )
    totals = [ProjectMetricDTO("all", "All uploads", total_rows)]
    totals.extend(
        ProjectMetricDTO(source.lower().replace(" ", "_"), source, count)
        for source, count in sorted(source_counts.items())
    )
    return ProjectUploadPageDTO(
        project=_project_dto(project),
        scope=_scope_dto(db, scope),
        rows=rows,
        lab_units=_scope_lab_units(db, scope),
        totals=tuple(totals),
        page=page,
        per_page=per_page,
        total_rows=total_rows,
    )


def get_direct_image_verification(
    db: Session, *, user: User, project_id: int, uuid: str
) -> DirectImageVerificationDTO:
    _project, scope = _project_and_scope(db, user=user, project_id=project_id)
    upload = db.execute(
        select(DirectImageUpload)
        .where(
            DirectImageUpload.project_id == project_id,
            DirectImageUpload.uuid == uuid,
            _direct_scope_clause(scope),
        )
        .options(
            selectinload(DirectImageUpload.disease),
            selectinload(DirectImageUpload.hospital),
            selectinload(DirectImageUpload.lab_unit),
            selectinload(DirectImageUpload.camera),
            selectinload(DirectImageUpload.area),
            selectinload(DirectImageUpload.uploader),
        )
    ).scalar_one_or_none()
    if upload is None or not can_verify_direct_images(
        db, user, project_id=project_id, lab_unit_id=upload.lab_unit_id
    ):
        raise ProjectReviewNotFound("Direct image not found.")
    verification = db.execute(select(DirectImageVerify).where(
        DirectImageVerify.image_upload_id == upload.id
    )).scalar_one_or_none()
    variant = "edited" if upload.edited_filename else "original"
    pii = db.execute(select(ImagePiiVerification).where(
        ImagePiiVerification.image_uuid == upload.uuid,
        ImagePiiVerification.image_variant == variant,
    )).scalar_one_or_none()
    return DirectImageVerificationDTO(
        project_id=project_id, upload_id=upload.id, uuid=upload.uuid,
        filename=upload.filename, image_url_uuid=upload.uuid,
        uploaded_at=upload.created_at, disease_name=upload.disease.name,
        hospital_name=upload.hospital.name, lab_unit_name=upload.lab_unit.name,
        camera_name=upload.camera.name, area_name=upload.area.name,
        uploader_name=upload.uploader.username,
        verification_status=verification.verified_status if verification else "pending",
        remarks=verification.remarks if verification else "",
        upload_remarks=upload.remarks,
        pii_status=pii.pii_status if pii else None,
        pii_source=pii.source if pii else None,
        pii_checked_at=pii.checked_at if pii else None,
        can_edit=can_manage_project_uploaders(
            db, user, project_id=project_id, lab_unit_id=upload.lab_unit_id
        ),
    )


def verify_direct_image(
    db: Session, *, user: User, project_id: int, uuid: str, status: str, remarks: str
) -> DirectImageVerificationDTO | None:
    current = get_direct_image_verification(db, user=user, project_id=project_id, uuid=uuid)
    if status not in {"verified", "not_gradable"}:
        raise ValueError("Unsupported verification status.")
    remarks = remarks.strip()
    if status == "not_gradable" and not remarks:
        raise ValueError("An ungradable reason is required.")
    if status == "verified" and current.pii_status == "detected":
        raise ValueError("PII is detected. Edit and clear the image before verification.")
    verification = db.execute(select(DirectImageVerify).where(
        DirectImageVerify.image_upload_id == current.upload_id
    )).scalar_one_or_none()
    if verification is None:
        verification = DirectImageVerify(image_upload_id=current.upload_id, verified_by_id=user.id)
        db.add(verification)
    verification.verified_status = status
    verification.remarks = remarks
    verification.verified_by_id = user.id
    verification.verified_at = func.now()
    db.flush()
    if status == "verified":
        from services.taskCreationServices import ensure_task
        upload = db.get(DirectImageUpload, current.upload_id)
        ensure_task(upload.uuid, upload.disease_id, db)
    next_uuid = db.execute(
        select(DirectImageUpload.uuid)
        .outerjoin(DirectImageVerify, DirectImageVerify.image_upload_id == DirectImageUpload.id)
        .where(
            DirectImageUpload.project_id == project_id,
            DirectImageUpload.lab_unit_id.in_(_project_and_scope(db, user=user, project_id=project_id)[1].lab_unit_ids or {-1}),
            or_(DirectImageVerify.id.is_(None), DirectImageVerify.verified_status.in_({"pending", "unverified"})),
            DirectImageUpload.id != current.upload_id,
        )
        .order_by(DirectImageUpload.created_at, DirectImageUpload.id)
        .limit(1)
    ).scalar_one_or_none()
    return get_direct_image_verification(
        db, user=user, project_id=project_id, uuid=next_uuid
    ) if next_uuid else None


def get_gradings(db: Session, *, user: User, project_id: int) -> ProjectGradingsDTO:
    project, scope = _project_and_scope(db, user=user, project_id=project_id)
    rows = _grading_rows(db, project.id, scope)
    return ProjectGradingsDTO(
        project=_project_dto(project),
        scope=_scope_dto(db, scope),
        rows=rows,
        totals=(
            ProjectMetricDTO("tasks", "Total tasks", sum(row.task_count for row in rows)),
            ProjectMetricDTO("images", "Task-image associations", sum(row.image_count for row in rows)),
            ProjectMetricDTO(
                "first_grading",
                "Awaiting first grading",
                sum(row.first_grading_count for row in rows),
            ),
            ProjectMetricDTO(
                "second_grading",
                "Awaiting second grading",
                sum(row.second_grading_count for row in rows),
            ),
            ProjectMetricDTO(
                "finalised",
                "Finalised tasks",
                sum(row.final_count for row in rows),
            ),
            ProjectMetricDTO(
                "adjudication",
                "Pending adjudication",
                sum(row.adjudication_count for row in rows),
            ),
        ),
    )


def _project_and_scope(db: Session, *, user: User, project_id: int) -> tuple[Project, _ResolvedScope]:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectReviewNotFound("Project not found.")
    configured_labs = configured_project_lab_unit_ids(db, project_id=project_id)
    if user.has_role("admin"):
        return project, _ResolvedScope(True, frozenset(), configured_labs)
    grants = db.execute(
        select(ProjectRoleGrant)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(PROJECT_ASSIGNABLE_ROLES),
        )
    ).scalars().all()
    if any(grant.scope_type == PROJECT_SCOPE for grant in grants):
        return project, _ResolvedScope(True, frozenset(), configured_labs)
    if not grants:
        raise ProjectReviewNotFound("Project not found.")
    return project, _ResolvedScope(
        False,
        frozenset(),
        (
            frozenset(grant.lab_unit_id for grant in grants if grant.scope_type == LAB_UNIT_SCOPE)
        ).intersection(configured_labs),
    )


def _allowed_lab_ids(db: Session, scope: _ResolvedScope) -> frozenset[int]:
    del db
    return scope.lab_unit_ids


def _encounter_scope_clause(scope: _ResolvedScope):
    if scope.project_wide:
        return PatientEncounters.lab_unit_id.in_(scope.lab_unit_ids or {-1})
    return PatientEncounters.lab_unit_id.in_(scope.lab_unit_ids or {-1})


def _direct_scope_clause(scope: _ResolvedScope):
    if scope.project_wide:
        return DirectImageUpload.lab_unit_id.in_(scope.lab_unit_ids or {-1})
    return DirectImageUpload.lab_unit_id.in_(scope.lab_unit_ids or {-1})


def _profile_configuration(db: Session, project_id: int) -> tuple[ProjectProfileDTO, ...]:
    mappings = db.execute(
        select(ProjectUploadProfile)
        .join(ProjectUploadProfile.profile)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
        )
        .options(
            selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.upload_kinds),
            selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.diseases).selectinload(UploadProfileDisease.disease),
            selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.encounter_set_types).selectinload(UploadProfileEncounterSetType.encounter_set_type),
            selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.encounter_set_types).selectinload(UploadProfileEncounterSetType.grading_packages),
            selectinload(ProjectUploadProfile.remidio_api_bindings),
        )
    ).scalars().unique().all()
    iitk_profile_ids = set(db.execute(select(IITKApiProjectConfig.project_upload_profile_id).where(
        IITKApiProjectConfig.project_id == project_id,
        IITKApiProjectConfig.active.is_(True),
    )).scalars())
    rows = []
    for mapping in mappings:
        profile = mapping.profile
        encounter_types = [entry for entry in profile.encounter_set_types if entry.active]
        packages = [
            f"{package.name} ({package.grading_mode.replace('_', ' ')})"
            for entry in encounter_types
            for package in entry.grading_packages
            if package.active
        ]
        rows.append(ProjectProfileDTO(
            name=profile.name,
            active=bool(mapping.active and profile.active),
            upload_kinds=tuple(sorted(kind.upload_kind for kind in profile.upload_kinds)),
            diseases=tuple(sorted(item.disease.name for item in profile.diseases)),
            encounter_set_types=tuple(sorted(item.encounter_set_type.name for item in encounter_types)),
            grading_packages=tuple(packages),
            remidio_api_enabled=bool(
                mapping.active and profile.active
                and any(binding.active for binding in mapping.remidio_api_bindings)
            ),
            iitk_enabled=bool(
                mapping.active and profile.active and mapping.id in iitk_profile_ids
            ),
        ))
    return tuple(sorted(rows, key=lambda row: (not row.active, row.name.lower())))


def _upload_rows(
    db: Session,
    project_id: int,
    scope: _ResolvedScope,
    *,
    page: int,
    per_page: int,
    status: str = "all",
    lab_unit_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    verifier_lab_unit_ids: frozenset[int] = frozenset(),
) -> tuple[tuple[ProjectUploadDTO, ...], int, dict[str, int]]:
    direct_status = func.coalesce(DirectImageVerify.verified_status, "pending")
    directs = select(
        literal("Single image").label("entity_type"),
        DirectImageUpload.uuid.label("uuid"),
        case(
            (DirectImageUpload.is_pregraded.is_(True), "Pre-graded image"),
            else_="Direct image",
        ).label("source"),
        Hospital.name.label("hospital_name"),
        LabUnit.name.label("lab_unit_name"),
        LabUnit.id.label("lab_unit_id"),
        direct_status.label("status"),
        literal(1).label("image_count"),
        DirectImageUpload.created_at.label("uploaded_at"),
        DirectImageUpload.id.label("upload_id"),
        DirectImageUpload.filename.label("filename"),
        User.username.label("uploader_name"),
        Disease.name.label("disease_name"),
        DirectImageUpload.remarks.label("upload_remarks"),
    ).join(
        LabUnit, LabUnit.id == DirectImageUpload.lab_unit_id
    ).join(Hospital, Hospital.id == DirectImageUpload.hospital_id).join(
        User, User.id == DirectImageUpload.uploader_id
    ).join(Disease, Disease.id == DirectImageUpload.disease_id).outerjoin(
        DirectImageVerify, DirectImageVerify.image_upload_id == DirectImageUpload.id
    ).where(
        DirectImageUpload.project_id == project_id,
        _direct_scope_clause(scope),
    )
    if lab_unit_id is not None:
        if lab_unit_id not in scope.lab_unit_ids:
            directs = directs.where(literal(False))
        else:
            directs = directs.where(DirectImageUpload.lab_unit_id == lab_unit_id)
    if status in {"pending", "verified", "not_gradable", "unverified"}:
        directs = directs.where(direct_status == status)
    if date_from is not None:
        directs = directs.where(DirectImageUpload.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        directs = directs.where(DirectImageUpload.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    inventory = directs.subquery("project_upload_inventory")
    total_rows = _scalar_count(db, select(func.count()).select_from(inventory))
    source_counts = dict(db.execute(select(
        inventory.c.source, func.count()
    ).group_by(inventory.c.source)).all())
    result = db.execute(select(inventory).order_by(
        inventory.c.uploaded_at.desc().nullslast(),
        inventory.c.uuid,
    ).offset((page - 1) * per_page).limit(per_page)).mappings().all()
    rows = tuple(ProjectUploadDTO(
        entity_type=row["entity_type"],
        uuid=row["uuid"],
        source=row["source"],
        hospital_name=row["hospital_name"],
        lab_unit_name=row["lab_unit_name"],
        lab_unit_id=row["lab_unit_id"],
        status=row["status"],
        image_count=int(row["image_count"] or 0),
        uploaded_at=row["uploaded_at"],
        upload_id=row["upload_id"],
        filename=row["filename"],
        uploader_name=row["uploader_name"],
        disease_name=row["disease_name"],
        upload_remarks=row["upload_remarks"],
        can_verify=row["lab_unit_id"] in verifier_lab_unit_ids,
    ) for row in result)
    return rows, total_rows, {source: int(count) for source, count in source_counts.items()}


def _scope_lab_units(db: Session, scope: _ResolvedScope) -> tuple[ProjectLabUnitChoiceDTO, ...]:
    rows = db.execute(
        select(LabUnit.id, LabUnit.name, Hospital.name)
        .join(Hospital, Hospital.id == LabUnit.hospital_id)
        .where(LabUnit.id.in_(scope.lab_unit_ids or {-1}))
        .order_by(Hospital.name, LabUnit.name)
    ).all()
    return tuple(ProjectLabUnitChoiceDTO(id=row[0], name=row[1], hospital_name=row[2]) for row in rows)


def _grading_rows(
    db: Session,
    project_id: int,
    scope: _ResolvedScope,
    *,
    top_level_only: bool = False,
) -> tuple[ProjectGradingDTO, ...]:
    allowed_labs = _allowed_lab_ids(db, scope)
    grouped: dict[tuple[str, str, str, str, str | None, str | None, str | None, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])

    def add_task(bucket: list[int], *, state: str, image_count: int) -> None:
        bucket[0] += 1
        bucket[1] += image_count
        if state in {"pending", "resident2_done"}:
            bucket[2] += 1
        elif state == "resident_done":
            bucket[3] += 1
        elif state == "arbitration":
            bucket[4] += 1
        elif state == "final":
            bucket[5] += 1

    if not top_level_only:
        direct_query = select(GradingTask, Disease).join(
            DirectImageUpload, DirectImageUpload.id == GradingTask.direct_image_upload_id
        ).join(Disease, Disease.id == GradingTask.disease_id).where(
            DirectImageUpload.project_id == project_id,
        )
        direct_query = direct_query.where(DirectImageUpload.lab_unit_id.in_(allowed_labs or {-1}))
        for task, disease in db.execute(direct_query):
            bucket = grouped[("Single images", "Independent image", "disease specific", "disease", None, None, None, disease.name)]
            add_task(bucket, state=task.state, image_count=1)

    scope_disease = aliased(Disease)
    parent_scope_disease = aliased(Disease)
    encounter_query = select(
        GradingTask,
        Disease,
        EncounterSetGradingPackage.grading_mode,
        EncounterSetGradingScope.link_role,
        scope_disease.name,
        parent_scope_disease.name,
        PatientEncounters.id,
        PatientEncounters.is_set_based,
    ).join(Disease, Disease.id == GradingTask.disease_id).outerjoin(
        EncounterSetGradingPackage,
        EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id,
    ).outerjoin(
        EncounterSetGradingScope,
        EncounterSetGradingScope.id == GradingTask.encounter_set_scope_id,
    ).outerjoin(
        scope_disease,
        scope_disease.id == EncounterSetGradingScope.scope_disease_id,
    ).outerjoin(
        parent_scope_disease,
        parent_scope_disease.id == EncounterSetGradingScope.parent_scope_disease_id,
    ).outerjoin(
        EncounterSetImage,
        EncounterSetImage.id == GradingTask.encounter_set_image_id,
    ).outerjoin(
        EncounterFile,
        EncounterFile.id == GradingTask.encounter_file_id,
    ).join(
        PatientEncounters,
        PatientEncounters.id == func.coalesce(
            GradingTask.patient_encounter_id,
            EncounterSetImage.patient_encounter_id,
            EncounterFile.patient_encounter_id,
        ),
    ).where(PatientEncounters.project_id == project_id)
    encounter_query = encounter_query.where(PatientEncounters.lab_unit_id.in_(allowed_labs or {-1}))
    if top_level_only:
        encounter_query = encounter_query.where(
            GradingTask.patient_encounter_id.is_not(None),
            or_(
                GradingTask.grading_target_level == "encounter",
                GradingTask.grading_target_level.is_(None),
            ),
        )
    encounter_image_counts = dict(db.execute(select(
        EncounterSetImage.patient_encounter_id,
        func.count(EncounterSetImage.id),
    ).join(PatientEncounters).where(
        PatientEncounters.project_id == project_id,
        _encounter_scope_clause(scope),
    ).group_by(EncounterSetImage.patient_encounter_id)).all())
    for task, disease, grading_mode, scope_role, scope_name, parent_scope_name, encounter_id, is_set_based in db.execute(encounter_query):
        if top_level_only and task.patient_encounter_id:
            if is_set_based:
                target_group, target = "EncounterSets", "Whole EncounterSet"
            else:
                target_group, target = "Classic ZIP encounters", "Whole encounter"
        elif task.encounter_set_image_id:
            target_group, target = "EncounterSets", "Image within EncounterSet"
        elif task.encounter_file_id and not is_set_based:
            target_group, target = "Classic ZIP encounters", "Individual image"
        elif task.encounter_file_id:
            target_group, target = "EncounterSets", "Image within EncounterSet"
        else:
            target_group, target = "EncounterSets", "Whole EncounterSet"
        mode = (grading_mode or "disease_specific").replace("_", " ")
        if scope_role in {"root", "linked"}:
            scope_type = "disease"
        elif scope_role == "unified" or grading_mode == "unified":
            scope_type = "encounter"
        elif grading_mode == "disease_specific":
            scope_type = "disease"
        else:
            scope_type = "legacy"
        bucket = grouped[(target_group, target, mode, scope_type, scope_role, scope_name, parent_scope_name, disease.name)]
        add_task(
            bucket,
            state=task.state,
            image_count=1 if task.encounter_set_image_id or task.encounter_file_id else int(encounter_image_counts.get(encounter_id, 0)),
        )

    return tuple(ProjectGradingDTO(
        target_group=key[0],
        target_type=key[1],
        grading_mode=key[2],
        scope_type=key[3],
        scope_role=key[4],
        scope_name=key[5],
        parent_scope_name=key[6],
        disease_name=key[7],
        task_count=value[0],
        image_count=value[1],
        first_grading_count=value[2],
        second_grading_count=value[3],
        adjudication_count=value[4],
        final_count=value[5],
        completion_percent=round((value[5] / value[0]) * 100) if value[0] else 0,
    ) for key, value in sorted(
        grouped.items(),
        key=lambda item: (
            {"EncounterSets": 0, "Single images": 1, "Classic ZIP encounters": 2}.get(item[0][0], 9),
            {"disease": 0, "encounter": 1, "legacy": 2}.get(item[0][3], 9),
            {"unified": 0, "root": 1, "linked": 2, None: 3}.get(item[0][4], 9),
            item[0][5] or "",
            {"Whole EncounterSet": 0, "Whole encounter": 0, "Image within EncounterSet": 1, "Independent image": 0, "Individual image": 0}.get(item[0][1], 9),
            item[0][7],
        ),
    ))


def _scope_dto(db: Session, scope: _ResolvedScope) -> ProjectScopeDTO:
    if scope.project_wide:
        label = "Project-wide"
    else:
        hospital_names = tuple(db.execute(select(Hospital.name).where(
            Hospital.id.in_(scope.hospital_ids)
        ).order_by(Hospital.name)).scalars()) if scope.hospital_ids else ()
        lab_names = tuple(db.execute(select(LabUnit.name).where(
            LabUnit.id.in_(scope.lab_unit_ids)
        ).order_by(LabUnit.name)).scalars()) if scope.lab_unit_ids else ()
        label = ", ".join((*hospital_names, *lab_names)) or "No data scope"
    return ProjectScopeDTO(scope.project_wide, tuple(sorted(scope.hospital_ids)), tuple(sorted(scope.lab_unit_ids)), label)


def _project_dto(project: Project) -> ProjectChoiceDTO:
    return ProjectChoiceDTO(project.id, project.title, project.code, project.active)


def _scalar_count(db: Session, statement) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def _report_count(db: Session, report_model, project_id: int, encounter_scope) -> int:
    return _scalar_count(db, select(func.count(report_model.id)).join(
        PatientEncounters,
        PatientEncounters.id == report_model.patient_encounter_id,
    ).where(PatientEncounters.project_id == project_id, encounter_scope))


def _wadhwani_count(db: Session, project_id: int, scope: _ResolvedScope) -> int:
    query = select(func.count(AIInferenceRun.id)).join(
        GradingTask, GradingTask.id == AIInferenceRun.task_id
    ).join(
        AIModelIntegration, AIModelIntegration.id == AIInferenceRun.integration_id
    ).outerjoin(
        DirectImageUpload,
        DirectImageUpload.id == GradingTask.direct_image_upload_id,
    ).outerjoin(
        EncounterSetImage,
        EncounterSetImage.id == GradingTask.encounter_set_image_id,
    ).outerjoin(
        EncounterFile,
        EncounterFile.id == GradingTask.encounter_file_id,
    ).outerjoin(
        PatientEncounters,
        PatientEncounters.id == func.coalesce(
            GradingTask.patient_encounter_id,
            EncounterSetImage.patient_encounter_id,
            EncounterFile.patient_encounter_id,
        ),
    ).where(
        AIModelIntegration.provider == "wadhwani_glaucoma",
        or_(
            DirectImageUpload.project_id == project_id,
            PatientEncounters.project_id == project_id,
        ),
    )
    allowed_labs = _allowed_lab_ids(db, scope)
    query = query.where(or_(
        DirectImageUpload.lab_unit_id.in_(allowed_labs or {-1}),
        PatientEncounters.lab_unit_id.in_(allowed_labs or {-1}),
    ))
    return _scalar_count(db, query)
