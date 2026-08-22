"""Scoped, non-PII read model for project summary, uploads, and gradings."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import DateTime, case, cast, exists, func, literal, or_, select, union_all
from sqlalchemy.orm import Session, selectinload

from data_authorization.models import HOSPITAL_SCOPE, LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from iitk_api_integration.models import IITKApiProjectConfig, IITKApiSessionLink
from models import (
    DirectImageUpload,
    Disease,
    DiabeticRetinopathyReport,
    AMDReport,
    GlaucomaReport,
    AIInferenceRun,
    AIModelIntegration,
    EncounterFile,
    EncounterSetGradingPackage,
    EncounterSetImage,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
    Project,
    ProjectInvestigator,
    User,
)
from remidio_api_integration.models import RemidioApiExamEncounter
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
)
from project_configuration.service import configured_project_lab_unit_ids
from project_configuration.models import ProjectLabUnit

from .dto import (
    ProjectChoiceDTO,
    ProjectGradingDTO,
    ProjectGradingsDTO,
    ProjectMetricDTO,
    ProjectProfileDTO,
    ProjectScopeDTO,
    ProjectSummaryDTO,
    ProjectUploadDTO,
    ProjectUploadPageDTO,
)
from .exceptions import ProjectReviewNotFound
from .configuration import effective_configuration


@dataclass(frozen=True)
class _ResolvedScope:
    project_wide: bool
    hospital_ids: frozenset[int]
    lab_unit_ids: frozenset[int]


STATE_LABELS = {
    "pending": "Not graded",
    "resident_done": "Pending Resident 2",
    "resident2_done": "Pending Resident",
    "arbitration": "Pending adjudication",
    "final": "Finalised",
}


def list_projects(db: Session, *, user: User) -> tuple[ProjectChoiceDTO, ...]:
    statement = select(Project).order_by(Project.active.desc(), Project.title)
    if not user.has_role("admin"):
        role_membership = exists().where(
            ProjectRoleGrant.project_id == Project.id,
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
        )
        upload_membership = exists().where(
            ProjectUploadProfile.project_id == Project.id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.id == ProjectUploadProfile.upload_profile_id,
            UploadProfile.active.is_(True),
            UploadProfile.automated_remidio_populated.is_(False),
            ProjectUploadProfileAssignment.project_upload_profile_id == ProjectUploadProfile.id,
            ProjectUploadProfileAssignment.user_id == user.id,
            ProjectUploadProfileAssignment.active.is_(True),
            ProjectLabUnit.project_id == Project.id,
            ProjectLabUnit.lab_unit_id == ProjectUploadProfileAssignment.lab_unit_id,
            ProjectLabUnit.active.is_(True),
        )
        legacy_membership = exists().where(
            ProjectInvestigator.project_id == Project.id,
            ProjectInvestigator.user_id == user.id,
            ProjectInvestigator.active.is_(True),
        )
        statement = statement.where(or_(role_membership, upload_membership, legacy_membership))
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
    set_image_count = _scalar_count(db, select(func.count(EncounterSetImage.id)).join(
        PatientEncounters, PatientEncounters.id == EncounterSetImage.patient_encounter_id
    ).where(PatientEncounters.project_id == project.id, encounter_scope))
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
    task_count = sum(row.task_count for row in _grading_rows(db, project.id, scope))
    report_counts = {
        "dr": _report_count(db, DiabeticRetinopathyReport, project.id, encounter_scope),
        "amd": _report_count(db, AMDReport, project.id, encounter_scope),
        "glaucoma": _report_count(db, GlaucomaReport, project.id, encounter_scope),
    }
    wadhwani_count = _wadhwani_count(db, project.id, scope)

    metrics = (
        ProjectMetricDTO("encounter_sets", "EncounterSets", encounter_count),
        ProjectMetricDTO("single_uploads", "Single-image uploads", direct_count),
        ProjectMetricDTO("total_images", "Total images", set_image_count + direct_count),
        ProjectMetricDTO("pregraded_images", "Pre-graded images", pregraded_count),
        ProjectMetricDTO("grading_packages", "EncounterSet packages", package_count),
        ProjectMetricDTO("grading_tasks", "Grading tasks", task_count),
        ProjectMetricDTO("remidio_dr_reports", "Remidio DR reports", report_counts["dr"]),
        ProjectMetricDTO("remidio_amd_reports", "Remidio AMD reports", report_counts["amd"]),
        ProjectMetricDTO("remidio_glaucoma_reports", "Remidio glaucoma reports", report_counts["glaucoma"]),
        ProjectMetricDTO("wadhwani_inferences", "Wadhwani glaucoma inferences", wadhwani_count),
    )
    allowed_labs = _allowed_lab_ids(db, scope)
    configuration = effective_configuration(
        db, project_id=project.id, allowed_lab_ids=allowed_labs
    )
    return ProjectSummaryDTO(
        project=_project_dto(project),
        scope=_scope_dto(db, scope),
        metrics=metrics,
        profiles=_profile_configuration(db, project.id),
        **configuration,
    )


def get_uploads(
    db: Session,
    *,
    user: User,
    project_id: int,
    page: int = 1,
    per_page: int = 100,
) -> ProjectUploadPageDTO:
    project, scope = _project_and_scope(db, user=user, project_id=project_id)
    page = max(1, page)
    per_page = min(200, max(1, per_page))
    rows, total_rows, source_counts = _upload_rows(
        db, project.id, scope, page=page, per_page=per_page
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
        totals=tuple(totals),
        page=page,
        per_page=per_page,
        total_rows=total_rows,
    )


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
                "not_graded",
                "Not graded",
                sum(row.task_count for row in rows if row.state == "pending"),
            ),
            ProjectMetricDTO(
                "resident2",
                "Pending Resident 2",
                sum(row.task_count for row in rows if row.state == "resident_done"),
            ),
            ProjectMetricDTO(
                "resident",
                "Pending Resident",
                sum(row.task_count for row in rows if row.state == "resident2_done"),
            ),
            ProjectMetricDTO(
                "finalised",
                "Finalised tasks",
                sum(row.task_count for row in rows if row.state == "final"),
            ),
            ProjectMetricDTO(
                "adjudication",
                "Pending adjudication",
                sum(row.task_count for row in rows if row.state == "arbitration"),
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
    grants = db.execute(select(ProjectRoleGrant).where(
        ProjectRoleGrant.project_id == project_id,
        ProjectRoleGrant.user_id == user.id,
        ProjectRoleGrant.active.is_(True),
    )).scalars().all()
    assignment_lab_ids = frozenset(db.execute(
        select(ProjectUploadProfileAssignment.lab_unit_id)
        .join(ProjectUploadProfile, ProjectUploadProfile.id == ProjectUploadProfileAssignment.project_upload_profile_id)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            ProjectUploadProfileAssignment.user_id == user.id,
            ProjectUploadProfileAssignment.active.is_(True),
        )
    ).scalars())
    legacy = db.execute(select(ProjectInvestigator.id).where(
        ProjectInvestigator.project_id == project_id,
        ProjectInvestigator.user_id == user.id,
        ProjectInvestigator.active.is_(True),
    ).limit(1)).scalar_one_or_none()
    if legacy is not None or any(grant.scope_type == PROJECT_SCOPE for grant in grants):
        return project, _ResolvedScope(True, frozenset(), configured_labs)
    if not grants and not assignment_lab_ids:
        raise ProjectReviewNotFound("Project not found.")
    hospital_ids = frozenset(
        grant.hospital_id for grant in grants if grant.scope_type == HOSPITAL_SCOPE
    )
    hospital_lab_ids = frozenset(db.execute(
        select(LabUnit.id).where(LabUnit.hospital_id.in_(hospital_ids or {-1}))
    ).scalars()).intersection(configured_labs)
    return project, _ResolvedScope(
        False,
        hospital_ids,
        (
            frozenset(grant.lab_unit_id for grant in grants if grant.scope_type == LAB_UNIT_SCOPE)
            | assignment_lab_ids
            | hospital_lab_ids
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
) -> tuple[tuple[ProjectUploadDTO, ...], int, dict[str, int]]:
    encounter_scope = _encounter_scope_clause(scope)
    image_count = select(func.count(EncounterSetImage.id)).where(
        EncounterSetImage.patient_encounter_id == PatientEncounters.id
    ).correlate(PatientEncounters).scalar_subquery()
    encounter_source = case(
        (exists().where(
            RemidioApiExamEncounter.patient_encounter_id == PatientEncounters.id
        ), "Remidio API"),
        (exists().where(
            IITKApiSessionLink.patient_encounter_id == PatientEncounters.id
        ), "IITK API"),
        (PatientEncounters.zip_file_id.isnot(None), "EncounterSet ZIP"),
        else_="EncounterSet",
    )
    from models import ZipFile

    encounters = select(
        literal("EncounterSet").label("entity_type"),
        PatientEncounters.uuid.label("uuid"),
        encounter_source.label("source"),
        Hospital.name.label("hospital_name"),
        LabUnit.name.label("lab_unit_name"),
        func.coalesce(PatientEncounters.encounter_verified_status, "pending").label("status"),
        image_count.label("image_count"),
        cast(ZipFile.upload_date, DateTime(timezone=True)).label("uploaded_at"),
    ).join(
        LabUnit, LabUnit.id == PatientEncounters.lab_unit_id
    ).join(Hospital, Hospital.id == LabUnit.hospital_id).where(
        PatientEncounters.project_id == project_id,
        PatientEncounters.is_set_based.is_(True),
        encounter_scope,
    ).outerjoin(ZipFile, ZipFile.id == PatientEncounters.zip_file_id)
    directs = select(
        literal("Single image").label("entity_type"),
        DirectImageUpload.uuid.label("uuid"),
        case(
            (DirectImageUpload.is_pregraded.is_(True), "Pre-graded image"),
            else_="Direct image",
        ).label("source"),
        Hospital.name.label("hospital_name"),
        LabUnit.name.label("lab_unit_name"),
        case(
            (DirectImageUpload.is_pregraded.is_(True), "pre-graded"),
            else_="uploaded",
        ).label("status"),
        literal(1).label("image_count"),
        DirectImageUpload.created_at.label("uploaded_at"),
    ).join(
        LabUnit, LabUnit.id == DirectImageUpload.lab_unit_id
    ).join(Hospital, Hospital.id == DirectImageUpload.hospital_id).where(
        DirectImageUpload.project_id == project_id,
        _direct_scope_clause(scope),
    )
    inventory = union_all(encounters, directs).subquery("project_upload_inventory")
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
        status=row["status"],
        image_count=int(row["image_count"] or 0),
        uploaded_at=row["uploaded_at"],
    ) for row in result)
    return rows, total_rows, {source: int(count) for source, count in source_counts.items()}


def _grading_rows(db: Session, project_id: int, scope: _ResolvedScope) -> tuple[ProjectGradingDTO, ...]:
    allowed_labs = _allowed_lab_ids(db, scope)
    grouped: dict[tuple[str, str, str, str], list[int]] = defaultdict(lambda: [0, 0])

    direct_query = select(GradingTask, Disease).join(
        DirectImageUpload, DirectImageUpload.id == GradingTask.direct_image_upload_id
    ).join(Disease, Disease.id == GradingTask.disease_id).where(
        DirectImageUpload.project_id == project_id,
    )
    direct_query = direct_query.where(DirectImageUpload.lab_unit_id.in_(allowed_labs or {-1}))
    for task, disease in db.execute(direct_query):
        bucket = grouped[("Single image", "disease specific", disease.name, task.state)]
        bucket[0] += 1
        bucket[1] += 1

    encounter_query = select(
        GradingTask,
        Disease,
        EncounterSetGradingPackage.grading_mode,
        PatientEncounters.id,
    ).join(Disease, Disease.id == GradingTask.disease_id).outerjoin(
        EncounterSetGradingPackage,
        EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id,
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
    encounter_image_counts = dict(db.execute(select(
        EncounterSetImage.patient_encounter_id,
        func.count(EncounterSetImage.id),
    ).join(PatientEncounters).where(
        PatientEncounters.project_id == project_id,
        _encounter_scope_clause(scope),
    ).group_by(EncounterSetImage.patient_encounter_id)).all())
    for task, disease, grading_mode, encounter_id in db.execute(encounter_query):
        target = "EncounterSet image" if task.encounter_set_image_id or task.encounter_file_id else "EncounterSet"
        mode = (grading_mode or "disease_specific").replace("_", " ")
        bucket = grouped[(target, mode, disease.name, task.state)]
        bucket[0] += 1
        bucket[1] += 1 if task.encounter_set_image_id or task.encounter_file_id else int(encounter_image_counts.get(encounter_id, 0))

    return tuple(ProjectGradingDTO(
        target_type=key[0],
        grading_mode=key[1],
        disease_name=key[2],
        state=key[3],
        state_label=STATE_LABELS.get(key[3], key[3].replace("_", " ").title()),
        task_count=value[0],
        image_count=value[1],
    ) for key, value in sorted(grouped.items()))


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
