"""Dataset lifecycle authorization over dataset-owned scope facts."""

from __future__ import annotations

import json

from sqlalchemy import false, select

from authz.behaviors import export_rows, role_scoped_rows
from authz.context import access_context
from data_authorization.models import ProjectRoleGrant
from models import (
    CuratedDataset,
    CuratedDatasetItem,
    GradingTask,
    LabUnit,
    Project,
    ProjectLabUnit,
    Role,
    User,
)
from project_configuration.service import project_site_feature_allows
from tasks.access import task_columns

DATASET_VIEW_ROLES = frozenset(
    {"dataset_creator", "data_manager", "data_exporter", "analytics_viewer"}
)
DATASET_MANAGE_ROLES = frozenset({"dataset_creator"})


def dataset_creation_projects(db, *, user: User) -> list[Project]:
    if user.has_role("admin"):
        return db.execute(select(Project).where(Project.active.is_(True)).order_by(Project.title)).scalars().all()
    return db.execute(
        select(Project)
        .join(ProjectRoleGrant, ProjectRoleGrant.project_id == Project.id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            Project.active.is_(True),
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            Role.name == "dataset_creator",
        )
        .distinct()
        .order_by(Project.title)
    ).scalars().all()


def dataset_creation_lab_unit_ids(
    db, *, user: User, context_kind: str, project_id: int | None
) -> frozenset[int]:
    if context_kind == "classical":
        if project_id is not None:
            return frozenset()
        if user.has_role("admin"):
            return frozenset(db.execute(select(LabUnit.id)).scalars().all())
        context = access_context(db, user)
        if "dataset_creator" not in context.global_roles:
            return frozenset()
        return context.assigned_lab_unit_ids
    if context_kind != "project" or not project_id:
        return frozenset()
    configured = frozenset(
        db.execute(
            select(ProjectLabUnit.lab_unit_id).where(
                ProjectLabUnit.project_id == project_id,
                ProjectLabUnit.active.is_(True),
            )
        ).scalars().all()
    )
    if user.has_role("admin"):
        return configured
    role_id = db.execute(select(Role.id).where(Role.name == "dataset_creator")).scalar_one_or_none()
    if role_id is None:
        return frozenset()
    grants = db.execute(
        select(ProjectRoleGrant.scope_type, ProjectRoleGrant.lab_unit_id).where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.role_id == role_id,
            ProjectRoleGrant.active.is_(True),
        )
    ).all()
    if any(scope_type == "project" for scope_type, _lab_id in grants):
        return configured
    granted = {
        lab_id for scope_type, lab_id in grants
        if scope_type == "lab_unit" and lab_id in configured
    }
    return frozenset(
        lab_id for lab_id in granted
        if project_site_feature_allows(
            db,
            project_id=project_id,
            lab_unit_id=lab_id,
            authority_scope_type="lab_unit",
            feature="sites_can_create_datasets",
        )
    )


def _scope_facts(dataset: CuratedDataset) -> tuple[int | None, frozenset[int]] | None:
    try:
        payload = json.loads(dataset.filters_json or "")
        raw_labs = payload["allowed_lab_units"]
        if not isinstance(raw_labs, list) or not raw_labs:
            return None
        lab_ids = frozenset(int(value) for value in raw_labs)
        if not lab_ids or any(value <= 0 for value in lab_ids):
            return None
        if dataset.context_kind not in {"classical", "project"}:
            return None
        project_id = dataset.project_id
        if dataset.context_kind == "classical" and project_id is not None:
            return None
        if dataset.context_kind == "project" and (project_id is None or project_id <= 0):
            return None
        return project_id, lab_ids
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def dataset_action_allowed(db, *, user: User, dataset: CuratedDataset, roles) -> bool:
    """Require every dataset task to remain in the actor's current action scope."""
    if not getattr(user, "is_active", False):
        return False
    if user.has_role("admin"):
        return True
    if dataset.admin_managed:
        return False
    facts = _scope_facts(dataset)
    if facts is None:
        return False
    _project_id, lab_ids = facts
    raw_base = (
        db.query(GradingTask.id)
        .join(CuratedDatasetItem, CuratedDatasetItem.task_id == GradingTask.id)
        .filter(CuratedDatasetItem.dataset_id == dataset.id)
    )
    total = raw_base.count()
    if total == 0:
        return (
            dataset.created_by_user_id == user.id
            and "dataset_creator" in frozenset(roles)
            and lab_ids.issubset(
                dataset_creation_lab_unit_ids(
                    db,
                    user=user,
                    context_kind=dataset.context_kind,
                    project_id=dataset.project_id,
                )
            )
        )
    base = raw_base
    if dataset.context_kind == "classical":
        base = base.filter(GradingTask.project_id.is_(None))
    else:
        base = base.filter(GradingTask.project_id == dataset.project_id)
    scoped = role_scoped_rows(
        base,
        access_context(db, user),
        task_columns(GradingTask),
        lab_roles=roles,
        hospital_roles=frozenset(),
        project_roles=roles,
        allow_admin=True,
    ).filter(GradingTask.lab_unit_id.in_(lab_ids))
    return scoped.count() == total


def dataset_site_feature_allowed(
    db, *, user: User, dataset: CuratedDataset, feature: str
) -> bool:
    """Apply project site flags to every Lab Unit represented by the dataset."""
    if user.has_role("admin"):
        return True
    facts = _scope_facts(dataset)
    if facts is None:
        return False
    project_id, lab_ids = facts
    if project_id is None:
        return True
    role_id = db.execute(select(Role.id).where(Role.name == "dataset_creator")).scalar_one_or_none()
    if role_id is None:
        return False
    grants = db.execute(
        select(ProjectRoleGrant.scope_type, ProjectRoleGrant.lab_unit_id).where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.role_id == role_id,
            ProjectRoleGrant.active.is_(True),
        )
    ).all()
    if any(scope_type == "project" for scope_type, _lab_id in grants):
        return True
    granted_labs = {
        lab_id for scope_type, lab_id in grants
        if scope_type == "lab_unit" and lab_id is not None
    }
    if not lab_ids.issubset(granted_labs):
        return False
    return all(
        project_site_feature_allows(
            db,
            project_id=project_id,
            lab_unit_id=lab_id,
            authority_scope_type="lab_unit",
            feature=feature,
        )
        for lab_id in lab_ids
    )


def can_view_dataset(db, *, user: User, dataset: CuratedDataset) -> bool:
    return dataset_action_allowed(db, user=user, dataset=dataset, roles=DATASET_VIEW_ROLES)


def can_manage_dataset(db, *, user: User, dataset: CuratedDataset) -> bool:
    return dataset_action_allowed(db, user=user, dataset=dataset, roles=DATASET_MANAGE_ROLES)


def can_share_dataset(db, *, user: User, dataset: CuratedDataset) -> bool:
    return can_manage_dataset(db, user=user, dataset=dataset) and dataset_site_feature_allowed(
        db, user=user, dataset=dataset, feature="sites_can_share_datasets"
    )


def can_export_dataset(db, *, user: User, dataset: CuratedDataset) -> bool:
    """Require export authority for every task selected in a dataset.

    Dataset visibility/curation authority is deliberately not sufficient for
    export.  The existing ``export_rows`` behaviour is the single source for
    ordinary export scope: a classical dataset needs ``data_exporter`` in the
    assigned Lab Units, while a project dataset needs a project-scoped
    ``data_exporter`` or ``pii_exporter`` grant.  Admin remains the explicit
    break-glass path, but dataset and task lineage must still be complete.
    """
    if not getattr(user, "is_active", False) or not getattr(dataset, "is_active", False):
        return False
    facts = _scope_facts(dataset)
    if facts is None:
        return False
    project_id, lab_ids = facts
    canonical_ids = valid_dataset_export_task_ids(db, dataset=dataset)
    if canonical_ids is None:
        return False
    if user.has_role("admin"):
        return True

    base = (
        db.query(GradingTask.id)
        .join(CuratedDatasetItem, CuratedDatasetItem.task_id == GradingTask.id)
        .filter(
            CuratedDatasetItem.dataset_id == dataset.id,
            CuratedDatasetItem.include_in_export.is_(True),
        )
        .distinct()
    )
    scoped = export_rows(
        db,
        base,
        user,
        task_columns(GradingTask),
    ).filter(GradingTask.lab_unit_id.in_(lab_ids))
    return scoped.count() == len(canonical_ids)


def valid_dataset_export_task_ids(
    db, *, dataset: CuratedDataset
) -> list[int] | None:
    """Return canonical task IDs only when every persisted lineage fact agrees."""
    facts = _scope_facts(dataset)
    if facts is None:
        return None
    project_id, lab_ids = facts
    canonical_ids = list(
        db.execute(
            select(CuratedDatasetItem.task_id).where(
                CuratedDatasetItem.dataset_id == dataset.id,
                CuratedDatasetItem.include_in_export.is_(True),
            )
        ).scalars()
    )
    if not canonical_ids or len(canonical_ids) != len(set(canonical_ids)):
        return None
    tasks = db.execute(
        select(GradingTask).where(GradingTask.id.in_(canonical_ids))
    ).scalars().all()
    if len(tasks) != len(canonical_ids):
        return None
    for task in tasks:
        source_count = sum(
            value is not None
            for value in (
                task.encounter_file_id,
                task.direct_image_upload_id,
                task.patient_encounter_id,
                task.encounter_set_image_id,
            )
        )
        if (
            source_count != 1
            or task.disease_id != dataset.disease_id
            or task.lab_unit_id not in lab_ids
            or task.project_id != project_id
        ):
            return None
    return canonical_ids


def scope_dataset_task_query(query, *, dataset: CuratedDataset):
    """Constrain attacker-supplied task IDs to the dataset's persisted context."""
    facts = _scope_facts(dataset)
    if facts is None:
        return query.filter(false())
    project_id, lab_ids = facts
    query = query.filter(GradingTask.lab_unit_id.in_(lab_ids))
    if dataset.context_kind == "classical":
        return query.filter(GradingTask.project_id.is_(None))
    return query.filter(GradingTask.project_id == project_id)
