"""Project/lab authorization for PII-enabled EncounterSet workflows."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import exists, func, or_, select, true
from sqlalchemy.orm import Session, aliased, selectinload

from data_authorization.service import project_role_grant_exists_clause, user_has_project_role
from models import LabUnit, Project, User, user_lab_units

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
    CAPABILITY_BROWSE: frozenset({"admin", "local_admin", "data_manager", "fileUploader", "optometrist"}),
    CAPABILITY_VERIFY: frozenset({"admin", "local_admin", "data_manager", "fileUploader", "optometrist"}),
    CAPABILITY_UPLOAD: frozenset({"admin", "local_admin", "data_manager", "fileUploader"}),
    CAPABILITY_DISCREPANCY_REVIEW: frozenset({"discrepancy_reviewer"}),
    # This capability currently protects the sole PII EMR reconciliation export.
    CAPABILITY_DATA_EXPORT: frozenset({"admin", "local_admin", "data_manager", "fileUploader", "optometrist"}),
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
    # System administrators retain break-glass access; all operational users
    # require an explicit project/lab capability row.
    if is_project_permission_admin(user):
        return query
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
    condition = or_(matching_role_grant, matching_permission)
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
    if is_project_permission_admin(user):
        return True
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
        project_id = encounter.project_id if encounter else None
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
    if capability not in CAPABILITY_COLUMNS:
        raise ValueError(f"Unknown project capability: {capability}")
    if is_project_permission_admin(user):
        return true()

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
    return task_scope.where(
        task.id == task_id_column,
        or_(project_id.is_(None), role_grant_exists, permission_exists),
    ).exists()


def list_project_permissions(
    db: Session,
    project_id: int,
    *,
    lab_unit_ids: set[int] | None = None,
) -> list[ProjectEncounterSetPermission]:
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
