"""Exact persisted-scope resolution and matching SQL query filters."""

from __future__ import annotations

from sqlalchemy import and_, false, or_, select

from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from models import Hospital, LabUnit, Project
from project_configuration.models import ProjectLabUnit


def resolve_scope(
    db,
    *,
    project_id: int | None = None,
    lab_unit_id: int | None = None,
    hospital_id: int | None = None,
    allow_system: bool = False,
) -> ScopeDTO | None:
    """Resolve one canonical scope without crossing project/classical ownership."""
    identifiers = (project_id, lab_unit_id, hospital_id)
    if any(
        value is not None and (not isinstance(value, int) or value <= 0)
        for value in identifiers
    ):
        return None
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None or not project.active:
            return None
        if lab_unit_id is None:
            return ScopeDTO(ScopeType.PROJECT, project_id, project_id=project_id)
        project_lab = db.execute(
            select(ProjectLabUnit).where(
                ProjectLabUnit.project_id == project_id,
                ProjectLabUnit.lab_unit_id == lab_unit_id,
            )
        ).scalar_one_or_none()
        if project_lab is None or not project_lab.active:
            return None
        lab = db.get(LabUnit, lab_unit_id)
        if lab is None:
            return None
        return ScopeDTO(
            ScopeType.PROJECT_LAB_UNIT,
            project_lab.id,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
            project_id=project_id,
            project_lab_unit_id=project_lab.id,
        )
    if lab_unit_id is not None:
        lab = db.get(LabUnit, lab_unit_id)
        if lab is None:
            return None
        return ScopeDTO(
            ScopeType.LAB_UNIT,
            lab.id,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
        )
    if hospital_id is not None:
        if db.get(Hospital, hospital_id) is None:
            return None
        return ScopeDTO(ScopeType.HOSPITAL, hospital_id, hospital_id=hospital_id)
    return ScopeDTO(ScopeType.SYSTEM) if allow_system else None


def admin_has_system_scope(grants) -> bool:
    """Only an Admin system grant is a global listing bypass."""
    return any(
        grant.active
        and grant.role is Role.ADMIN
        and grant.scope.scope_type is ScopeType.SYSTEM
        for grant in grants
    )


def scope_model_query(model, grants, query):
    """Apply SQL predicates equivalent to ``ScopeDTO.contains``.

    Classical hospital/lab grants explicitly exclude project-owned rows. Project
    grants include their stored project sites. A non-Admin system grant never
    becomes an accidental global bypass.
    """
    if admin_has_system_scope(grants):
        return query

    columns = model.__table__.columns
    has_project = "project_id" in columns
    has_lab = "lab_unit_id" in columns
    has_hospital = "hospital_id" in columns
    clauses = []

    project_ids = {
        grant.scope.project_id or grant.scope.scope_id
        for grant in grants
        if grant.active
        and grant.scope.scope_type is ScopeType.PROJECT
        and (grant.scope.project_id or grant.scope.scope_id) is not None
    }
    project_sites = {
        (
            grant.scope.project_id,
            grant.scope.lab_unit_id,
        )
        for grant in grants
        if grant.active
        and grant.scope.scope_type is ScopeType.PROJECT_LAB_UNIT
        and grant.scope.project_id is not None
        and grant.scope.lab_unit_id is not None
    }
    if has_project and project_ids:
        clauses.append(model.project_id.in_(project_ids))
    if has_project and has_lab:
        clauses.extend(
            and_(model.project_id == project_id, model.lab_unit_id == lab_id)
            for project_id, lab_id in project_sites
        )

    lab_ids = {
        grant.scope.lab_unit_id or grant.scope.scope_id
        for grant in grants
        if grant.active
        and grant.scope.scope_type is ScopeType.LAB_UNIT
        and (grant.scope.lab_unit_id or grant.scope.scope_id) is not None
    }
    if has_lab and lab_ids:
        classical = model.lab_unit_id.in_(lab_ids)
        if has_project:
            classical = and_(model.project_id.is_(None), classical)
        clauses.append(classical)

    hospital_ids = {
        grant.scope.hospital_id or grant.scope.scope_id
        for grant in grants
        if grant.active
        and grant.scope.scope_type is ScopeType.HOSPITAL
        and (grant.scope.hospital_id or grant.scope.scope_id) is not None
    }
    if hospital_ids:
        if has_hospital:
            classical = model.hospital_id.in_(hospital_ids)
        elif has_lab:
            classical = model.lab_unit_id.in_(
                select(LabUnit.id).where(LabUnit.hospital_id.in_(hospital_ids))
            )
        else:
            classical = None
        if classical is not None:
            if has_project:
                classical = and_(model.project_id.is_(None), classical)
            clauses.append(classical)

    return query.where(or_(*clauses)) if clauses else query.where(false())
