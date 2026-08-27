"""Authoritative project and project-site resolvers."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import false, or_

from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import ScopeType
from authz_v2.resources.references import AutomationTargetRef, is_positive_int
from authz_v2.resources.registry import ResourceAdapter, ResourceTarget
from authz_v2.resources.scoping import admin_has_system_scope
from models import LabUnit, Project
from project_configuration.models import ProjectLabUnit


def resolve_project(db, resource_id: object) -> ResourceTarget | None:
    automation_rule_id = None
    if isinstance(resource_id, AutomationTargetRef):
        if not is_positive_int(resource_id.automation_rule_id):
            return None
        automation_rule_id = resource_id.automation_rule_id
        resource_id = resource_id.target
    if not is_positive_int(resource_id):
        return None
    project = db.get(Project, resource_id)
    if project is None or not project.active:
        return None
    scope = ScopeDTO(ScopeType.PROJECT, project.id, project_id=project.id)
    return ResourceTarget(
        project,
        ResourceContextDTO(
            "project",
            project.id,
            scope,
            state={
                "target_active": bool(project.active),
                **(
                    {"automation_rule_id": automation_rule_id}
                    if automation_rule_id is not None
                    else {}
                ),
            },
            resolved=True,
        ),
    )


def resolve_project_upload_target(db, resource_id: object) -> ResourceTarget | None:
    if not is_positive_int(resource_id):
        return None
    project_lab = db.get(ProjectLabUnit, resource_id)
    if project_lab is None or not project_lab.active:
        return None
    lab = db.get(LabUnit, project_lab.lab_unit_id)
    project = db.get(Project, project_lab.project_id)
    if lab is None or project is None or not project.active:
        return None
    scope = ScopeDTO(
        ScopeType.PROJECT_LAB_UNIT,
        project_lab.id,
        hospital_id=lab.hospital_id,
        lab_unit_id=lab.id,
        project_id=project.id,
        project_lab_unit_id=project_lab.id,
    )
    return ResourceTarget(
        project_lab,
        ResourceContextDTO(
            "project_upload_target",
            project_lab.id,
            scope,
            state={"target_active": bool(project.active and project_lab.active)},
            resolved=True,
        ),
    )


def scope_projects(_db, _principal, _action, grants, query):
    if admin_has_system_scope(grants):
        return query
    project_ids = {
        grant.scope.project_id or grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type in {ScopeType.PROJECT, ScopeType.PROJECT_LAB_UNIT}
    }
    return (
        query.where(Project.id.in_(project_ids))
        if project_ids
        else query.where(false())
    )


def scope_project_sites(_db, _principal, _action, grants, query):
    if admin_has_system_scope(grants):
        return query
    project_ids = {
        grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type is ScopeType.PROJECT
        and grant.scope.scope_id is not None
    }
    site_ids = {
        grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type is ScopeType.PROJECT_LAB_UNIT
        and grant.scope.scope_id is not None
    }
    clauses = []
    if project_ids:
        clauses.append(ProjectLabUnit.project_id.in_(project_ids))
    if site_ids:
        clauses.append(ProjectLabUnit.id.in_(site_ids))
    return query.where(or_(*clauses)) if clauses else query.where(false())


def project_facts(_db, _principal, _action, target, facts):
    return replace(facts, domain_valid=bool(getattr(target.value, "active", False)))


PROJECT_ADAPTER = ResourceAdapter(
    "project", resolve_project, scope_projects, project_facts
)
PROJECT_UPLOAD_TARGET_ADAPTER = ResourceAdapter(
    "project_upload_target", resolve_project_upload_target, scope_project_sites
)
