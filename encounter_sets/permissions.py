"""EncounterSet workflow capability scoping and legacy compatibility.

This module remains the source for legacy ``ProjectEncounterSetPermission``
capabilities and collaborator relationships. New cross-resource decisions are
made by :mod:`authz`; media authorization imports only the narrow relationship
resolvers below instead of duplicating capability queries or role mappings.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, func, or_, select, true
from sqlalchemy.orm import Session, aliased, selectinload

from data_authorization.service import project_role_grant_exists_clause, user_has_project_role
from data_authorization.models import (
    HOSPITAL_SCOPE,
    LAB_UNIT_SCOPE,
    PROJECT_SCOPE,
    ProjectRoleGrant,
)
from models import LabUnit, Project, Role, User, user_lab_units
from project_configuration.models import ProjectLabUnit

from .models import ProjectEncounterSetPermission


CAPABILITY_BROWSE = "browse"
CAPABILITY_VERIFY = "verify"
CAPABILITY_UPLOAD = "upload"
CAPABILITY_DISCREPANCY_REVIEW = "discrepancy_review"
CAPABILITY_DATA_EXPORT = "data_export"
CAPABILITY_ANALYTICS_VIEW = "analytics_view"
CAPABILITY_DATASET_CREATION = "dataset_creation"
CAPABILITY_REGRADE_ADJUDICATION = "regrade_adjudication"

CAPABILITY_COLUMNS = {
    CAPABILITY_BROWSE: ProjectEncounterSetPermission.can_browse,
    CAPABILITY_VERIFY: ProjectEncounterSetPermission.can_verify,
    CAPABILITY_UPLOAD: ProjectEncounterSetPermission.can_upload,
    CAPABILITY_DISCREPANCY_REVIEW: ProjectEncounterSetPermission.can_review_discrepancies,
    CAPABILITY_DATA_EXPORT: ProjectEncounterSetPermission.can_export_data,
    CAPABILITY_ANALYTICS_VIEW: ProjectEncounterSetPermission.can_view_analytics,
    CAPABILITY_DATASET_CREATION: ProjectEncounterSetPermission.can_create_datasets,
    CAPABILITY_REGRADE_ADJUDICATION: ProjectEncounterSetPermission.can_adjudicate_regrades,
}

CAPABILITY_ROLES = {
    CAPABILITY_BROWSE: frozenset({
        "admin", "local_admin", "data_manager", "fileUploader", "optometrist",
        "field_optometrist", "field_ophthalmologist",
    }),
    CAPABILITY_VERIFY: frozenset({
        "verifier",
        "admin", "local_admin", "data_manager", "fileUploader",
        "field_optometrist", "field_ophthalmologist",
    }),
    CAPABILITY_UPLOAD: frozenset({"admin", "local_admin", "data_manager", "fileUploader"}),
    CAPABILITY_DISCREPANCY_REVIEW: frozenset({"discrepancy_reviewer"}),
    # This capability currently protects the sole PII EMR reconciliation export.
    CAPABILITY_DATA_EXPORT: frozenset({
        "admin", "local_admin", "data_manager", "data_exporter", "fileUploader", "optometrist"
    }),
    CAPABILITY_ANALYTICS_VIEW: frozenset({"admin", "local_admin", "data_manager", "analytics_viewer"}),
    CAPABILITY_DATASET_CREATION: frozenset({"admin", "dataset_creator"}),
    CAPABILITY_REGRADE_ADJUDICATION: frozenset({"regrade_adjudicator"}),
}


def is_project_permission_admin(user: User) -> bool:
    """Return whether the user has break-glass project workflow access."""
    return bool(getattr(user, "is_master_admin", False) or user.has_role("admin"))


class EncounterSetPermissionError(ValueError):
    """Raised when a project EncounterSet permission cannot be saved."""


@dataclass(frozen=True)
class ProjectEncounterSetPermissionInput:
    """Validated input contract for one legacy project capability row."""

    user_id: int
    lab_unit_id: int
    can_browse: bool
    can_verify: bool
    can_upload: bool = False
    can_review_discrepancies: bool = False
    can_export_data: bool = False
    can_view_analytics: bool = False
    can_create_datasets: bool = False
    can_adjudicate_regrades: bool = False
    active: bool = True


def _explicit_lab_unit_ids(db: Session, user_id: int) -> set[int]:
    return set(db.execute(
        select(user_lab_units.c.lab_unit_id).where(user_lab_units.c.user_id == user_id)
    ).scalars().all())


def apply_project_permission_scope(query, model_class, user: User, capability: str):
    """Restrict an EncounterSet query to explicitly authorized project/lab rows."""
    if capability not in CAPABILITY_COLUMNS:
        raise ValueError(f"Unknown EncounterSet capability: {capability}")
    # System administrators retain break-glass access, which means exactly
    # that: no filter at all. Applying the project boundary to them would
    # hide rows whose lab has since been removed from the project from the
    # only people able to put that right. Operational users need both the
    # boundary and an explicit project/lab capability row.
    if is_project_permission_admin(user):
        return query
    project_boundary = exists().where(
        ProjectLabUnit.project_id == model_class.project_id,
        ProjectLabUnit.lab_unit_id == model_class.lab_unit_id,
        ProjectLabUnit.active.is_(True),
    )
    capability_clause = CAPABILITY_COLUMNS[capability].is_(True)
    if capability == CAPABILITY_BROWSE:
        capability_clause = (
            ProjectEncounterSetPermission.can_browse.is_(True)
            | ProjectEncounterSetPermission.can_verify.is_(True)
        )
    matching_permission = exists().where(
        ProjectEncounterSetPermission.project_id == model_class.project_id,
        ProjectEncounterSetPermission.lab_unit_id == model_class.lab_unit_id,
        ProjectEncounterSetPermission.user_id == user.id,
        ProjectEncounterSetPermission.active.is_(True),
        capability_clause,
    )
    matching_role_grant = project_role_grant_exists_clause(
        user_id=user.id,
        project_id=model_class.project_id,
        role_names=CAPABILITY_ROLES[capability],
        hospital_id=getattr(model_class, "hospital_id", None),
        lab_unit_id=getattr(model_class, "lab_unit_id", None),
    )
    condition = and_(project_boundary, or_(matching_role_grant, matching_permission))
    if hasattr(query, "filter"):
        return query.filter(condition)
    return query.where(condition)


def apply_classical_or_project_permission_scope(
    query,
    model_class,
    user: User,
    capability: str,
    *,
    classical_operation: str,
):
    """Keep classical and project authorization paths separate, then combine them.

    Non-project rows use the established hospital/lab-unit scoper. Project rows
    use only an explicit project role grant or the legacy project permission
    compatibility row. This helper currently targets ORM ``Query`` callers.
    """
    if not hasattr(query, "session") or query.session is None:
        raise TypeError("Classical/project combined scoping requires an ORM Query.")
    if not hasattr(model_class, "project_id"):
        raise TypeError("Combined project scoping requires a project_id column.")

    from utils.hospital_scoping import apply_scoping

    classical_ids = query.session.query(model_class.id).filter(
        model_class.project_id.is_(None)
    )
    classical_ids = apply_scoping(
        classical_ids,
        model_class,
        user,
        classical_operation,
    )
    project_ids = apply_project_permission_scope(
        query.session.query(model_class.id).filter(model_class.project_id.isnot(None)),
        model_class,
        user,
        capability,
    )
    return query.filter(or_(
        model_class.id.in_(classical_ids),
        model_class.id.in_(project_ids),
    ))


def user_has_task_capability(
    db: Session,
    *,
    user: User,
    task_id: int,
    capability: str,
) -> bool:
    """Authorize a polymorphic grading task using its source project's lineage."""
    if capability not in CAPABILITY_COLUMNS:
        raise ValueError(f"Unknown project capability: {capability}")
    from models import DirectImageUpload, EncounterFile, EncounterSetImage, GradingTask, PatientEncounters

    task = db.get(GradingTask, task_id)
    if task is None:
        return False
    project_id = None
    if task.patient_encounter_id:
        encounter = db.get(PatientEncounters, task.patient_encounter_id)
        project_id = encounter.project_id if encounter else None
    elif task.encounter_set_image_id:
        image = db.get(EncounterSetImage, task.encounter_set_image_id)
        encounter = db.get(PatientEncounters, image.patient_encounter_id) if image else None
        project_id = (image.project_id if image else None) or (
            encounter.project_id if encounter else None
        )
    elif task.encounter_file_id:
        image = db.get(EncounterFile, task.encounter_file_id)
        project_id = image.project_id if image else None
        if project_id is None and image:
            encounter = db.get(PatientEncounters, image.patient_encounter_id)
            project_id = encounter.project_id if encounter else None
    elif task.direct_image_upload_id:
        image = db.get(DirectImageUpload, task.direct_image_upload_id)
        project_id = image.project_id if image else None
    if project_id is None:
        return True
    from project_configuration.service import configured_project_lab_unit_ids

    if task.lab_unit_id not in configured_project_lab_unit_ids(db, project_id=project_id):
        return False
    if is_project_permission_admin(user):
        return True
    legacy_permission = db.execute(
        select(ProjectEncounterSetPermission.id).where(
            ProjectEncounterSetPermission.project_id == project_id,
            ProjectEncounterSetPermission.lab_unit_id == task.lab_unit_id,
            ProjectEncounterSetPermission.user_id == user.id,
            ProjectEncounterSetPermission.active.is_(True),
            CAPABILITY_COLUMNS[capability].is_(True),
        )
    ).scalar_one_or_none() is not None
    return legacy_permission or user_has_project_role(
        db,
        user_id=user.id,
        project_id=project_id,
        role_names=CAPABILITY_ROLES[capability],
        lab_unit_id=task.lab_unit_id,
    )


def project_task_capability_clause(task_id_column, user: User, capability: str):
    """Build a SQL clause for project authorization of polymorphic grading tasks."""
    return _project_task_capability_clause(
        task_id_column,
        user,
        capability,
        allow_classical=True,
    )


def _project_task_capability_clause(
    task_id_column,
    user: User,
    capability: str,
    *,
    allow_classical: bool,
):
    """Build project capability SQL with an explicit classical-data boundary."""
    if capability not in CAPABILITY_COLUMNS:
        raise ValueError(f"Unknown project capability: {capability}")
    from models import DirectImageUpload, EncounterFile, EncounterSetImage, GradingTask, PatientEncounters

    task = aliased(GradingTask)
    task_encounter = aliased(PatientEncounters)
    set_image = aliased(EncounterSetImage)
    set_encounter = aliased(PatientEncounters)
    encounter_file = aliased(EncounterFile)
    file_encounter = aliased(PatientEncounters)
    direct_image = aliased(DirectImageUpload)
    project_id = func.coalesce(
        task_encounter.project_id,
        set_image.project_id,
        set_encounter.project_id,
        encounter_file.project_id,
        file_encounter.project_id,
        direct_image.project_id,
    )
    permission_exists = exists().where(
        ProjectEncounterSetPermission.project_id == project_id,
        ProjectEncounterSetPermission.lab_unit_id == task.lab_unit_id,
        ProjectEncounterSetPermission.user_id == user.id,
        ProjectEncounterSetPermission.active.is_(True),
        CAPABILITY_COLUMNS[capability].is_(True),
    )
    role_grant_exists = project_role_grant_exists_clause(
        user_id=user.id,
        project_id=project_id,
        role_names=CAPABILITY_ROLES[capability],
        lab_unit_id=task.lab_unit_id,
    )
    project_boundary = exists().where(
        ProjectLabUnit.project_id == project_id,
        ProjectLabUnit.lab_unit_id == task.lab_unit_id,
        ProjectLabUnit.active.is_(True),
    )
    task_scope = select(1).select_from(task).outerjoin(
        task_encounter, task_encounter.id == task.patient_encounter_id
    ).outerjoin(
        set_image, set_image.id == task.encounter_set_image_id
    ).outerjoin(
        set_encounter, set_encounter.id == set_image.patient_encounter_id
    ).outerjoin(
        encounter_file, encounter_file.id == task.encounter_file_id
    ).outerjoin(
        file_encounter, file_encounter.id == encounter_file.patient_encounter_id
    ).outerjoin(
        direct_image, direct_image.id == task.direct_image_upload_id
    )
    # Break-glass again: an administrator is not narrowed by the boundary.
    authorization = true() if is_project_permission_admin(user) else and_(
        project_boundary,
        or_(role_grant_exists, permission_exists),
    )
    if allow_classical:
        authorization = or_(project_id.is_(None), authorization)
    else:
        authorization = and_(project_id.isnot(None), authorization)
    return task_scope.where(task.id == task_id_column, authorization).exists()


def capability_lab_unit_ids(
    db: Session,
    *,
    user: User,
    capability: str,
) -> set[int]:
    """Return classical and project-scoped labs available for a capability."""
    if capability not in CAPABILITY_COLUMNS:
        raise ValueError(f"Unknown project capability: {capability}")
    if is_project_permission_admin(user):
        return set(db.execute(
            select(ProjectLabUnit.lab_unit_id).where(ProjectLabUnit.active.is_(True))
        ).scalars())

    lab_unit_ids: set[int] = set()
    if user.has_role(*CAPABILITY_ROLES[capability]):
        lab_unit_ids.update(db.execute(
            select(user_lab_units.c.lab_unit_id).where(
                user_lab_units.c.user_id == user.id
            )
        ).scalars())

    legacy_labs = db.execute(
        select(ProjectEncounterSetPermission.lab_unit_id).where(
            ProjectEncounterSetPermission.user_id == user.id,
            ProjectEncounterSetPermission.active.is_(True),
            CAPABILITY_COLUMNS[capability].is_(True),
        )
    ).scalars()
    lab_unit_ids.update(legacy_labs)

    grants = db.execute(
        select(ProjectRoleGrant)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(CAPABILITY_ROLES[capability]),
        )
    ).scalars().all()
    for grant in grants:
        configured_labs = select(ProjectLabUnit.lab_unit_id).where(
            ProjectLabUnit.project_id == grant.project_id,
            ProjectLabUnit.active.is_(True),
        )
        if grant.scope_type == PROJECT_SCOPE:
            lab_unit_ids.update(db.execute(configured_labs).scalars())
        elif grant.scope_type == HOSPITAL_SCOPE and grant.hospital_id is not None:
            lab_unit_ids.update(db.execute(
                configured_labs.join(
                    LabUnit,
                    LabUnit.id == ProjectLabUnit.lab_unit_id,
                ).where(LabUnit.hospital_id == grant.hospital_id)
            ).scalars())
        elif grant.scope_type == LAB_UNIT_SCOPE and grant.lab_unit_id is not None:
            if db.execute(
                configured_labs.where(ProjectLabUnit.lab_unit_id == grant.lab_unit_id)
            ).scalar_one_or_none() is not None:
                lab_unit_ids.add(grant.lab_unit_id)
    return lab_unit_ids


def legacy_project_capabilities_for_scope(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    lab_unit_id: int,
) -> frozenset[str]:
    """Return capabilities from the legacy project-permission compatibility row."""
    row = db.execute(select(ProjectEncounterSetPermission).where(
        ProjectEncounterSetPermission.user_id == user_id,
        ProjectEncounterSetPermission.project_id == project_id,
        ProjectEncounterSetPermission.lab_unit_id == lab_unit_id,
        ProjectEncounterSetPermission.active.is_(True),
        exists().where(
            ProjectLabUnit.project_id == project_id,
            ProjectLabUnit.lab_unit_id == lab_unit_id,
            ProjectLabUnit.active.is_(True),
        ),
    )).scalar_one_or_none()
    if row is None:
        return frozenset()
    return frozenset(
        capability
        for capability, column in CAPABILITY_COLUMNS.items()
        if bool(getattr(row, column.key))
    )


def user_is_legacy_project_collaborator(
    db: Session,
    *,
    user_id: int,
    project_id: int,
) -> bool:
    """Preserve legacy ProjectInvestigator collaborator membership during migration."""
    from models import ProjectInvestigator

    return db.execute(select(ProjectInvestigator.id).where(
        ProjectInvestigator.user_id == user_id,
        ProjectInvestigator.project_id == project_id,
        ProjectInvestigator.role == "collaborator",
        ProjectInvestigator.active.is_(True),
    )).scalar_one_or_none() is not None


def legacy_collaborator_project_ids(db: Session, *, user_id: int) -> frozenset[int]:
    """Every project where the user holds legacy ProjectInvestigator collaborator membership.

    The set form of ``user_is_legacy_project_collaborator``, for callers that
    resolve all of a user's relationships at once.
    """
    from models import ProjectInvestigator

    return frozenset(db.execute(select(ProjectInvestigator.project_id).where(
        ProjectInvestigator.user_id == user_id,
        ProjectInvestigator.role == "collaborator",
        ProjectInvestigator.active.is_(True),
    )).scalars())


def apply_task_capability_scope(
    query,
    task_entity,
    user: User,
    capability: str,
):
    """Scope a polymorphic task query across classical and project authority."""
    if is_project_permission_admin(user):
        return query
    if not hasattr(query, "session") or query.session is None:
        raise TypeError("Task capability scoping requires an ORM Query.")
    allowed_lab_ids = capability_lab_unit_ids(
        query.session,
        user=user,
        capability=capability,
    )
    if not allowed_lab_ids:
        return query.filter(task_entity.id.is_(None))
    allow_classical = user.has_role(*CAPABILITY_ROLES[capability])
    return query.filter(
        task_entity.lab_unit_id.in_(allowed_lab_ids),
        _project_task_capability_clause(
            task_entity.id,
            user,
            capability,
            allow_classical=allow_classical,
        ),
    )


def list_project_permissions(
    db: Session,
    project_id: int,
    *,
    lab_unit_ids: set[int] | None = None,
) -> list[ProjectEncounterSetPermission]:
    """List project capability rows, optionally constrained to allowed labs."""
    statement = select(ProjectEncounterSetPermission).where(
        ProjectEncounterSetPermission.project_id == project_id
    )
    if lab_unit_ids is not None:
        statement = statement.where(
            ProjectEncounterSetPermission.lab_unit_id.in_(lab_unit_ids)
        )
    return (
        db.execute(
            statement
            .options(
                selectinload(ProjectEncounterSetPermission.user),
                selectinload(ProjectEncounterSetPermission.lab_unit).selectinload(LabUnit.hospital),
            )
            .order_by(
                ProjectEncounterSetPermission.active.desc(),
                ProjectEncounterSetPermission.lab_unit_id,
                ProjectEncounterSetPermission.user_id,
            )
        )
        .scalars()
        .all()
    )


def set_project_permission(
    db: Session,
    *,
    manager_user_id: int,
    project_id: int,
    data: ProjectEncounterSetPermissionInput,
) -> ProjectEncounterSetPermission:
    """Create or replace one user's permissions for a project/lab combination."""
    manager = db.get(User, manager_user_id)
    project = db.get(Project, project_id)
    target_user = db.get(User, data.user_id)
    lab_unit = db.get(LabUnit, data.lab_unit_id)
    if manager is None or project is None or target_user is None or lab_unit is None:
        raise EncounterSetPermissionError("Project, user, or lab unit was not found.")
    if not target_user.is_active:
        raise EncounterSetPermissionError("EncounterSet access can only be assigned to an active user.")

    manager_labs = _explicit_lab_unit_ids(db, manager_user_id)
    if data.lab_unit_id not in manager_labs:
        raise EncounterSetPermissionError("You cannot manage permissions outside your assigned lab units.")
    target_labs = _explicit_lab_unit_ids(db, data.user_id)
    if data.lab_unit_id not in target_labs:
        raise EncounterSetPermissionError("The selected user is not assigned to that lab unit.")

    row = db.execute(
        select(ProjectEncounterSetPermission).where(
            ProjectEncounterSetPermission.project_id == project_id,
            ProjectEncounterSetPermission.user_id == data.user_id,
            ProjectEncounterSetPermission.lab_unit_id == data.lab_unit_id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = ProjectEncounterSetPermission(
            project_id=project_id,
            user_id=data.user_id,
            lab_unit_id=data.lab_unit_id,
        )
        db.add(row)
    row.can_browse = data.can_browse
    row.can_verify = data.can_verify
    row.can_upload = data.can_upload
    row.can_review_discrepancies = data.can_review_discrepancies
    row.can_export_data = data.can_export_data
    row.can_view_analytics = data.can_view_analytics
    row.can_create_datasets = data.can_create_datasets
    row.can_adjudicate_regrades = data.can_adjudicate_regrades
    row.active = data.active and any((
        data.can_browse,
        data.can_verify,
        data.can_upload,
        data.can_review_discrepancies,
        data.can_export_data,
        data.can_view_analytics,
        data.can_create_datasets,
        data.can_adjudicate_regrades,
    ))
    db.flush()
    return row
