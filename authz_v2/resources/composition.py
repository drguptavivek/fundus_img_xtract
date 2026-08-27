"""Application-owned registration of concrete authorization resource adapters."""

from __future__ import annotations

from dataclasses import replace

from authz_v2.core.actions import Action
from authz_v2.core.choices import ChoiceListDTO
from authz_v2.resources.adapters import RESOURCE_ADAPTERS
from authz_v2.resources.grants import GRANT_TARGET_ADAPTER
from authz_v2.resources.projects import (
    PROJECT_ADAPTER,
    PROJECT_UPLOAD_TARGET_ADAPTER,
    resolve_project,
    scope_projects,
)
from authz_v2.resources.registry import (
    ChoiceRegistry,
    ResourceAdapter,
    ResourceRegistry,
)
from authz_v2.resources.relationships import (
    automation_rule_facts,
    compose_facts,
    upload_profile_facts,
)
from authz_v2.resources.upload_targets import resolve_project_upload_target
from authz_v2.resources.users import USER_ADAPTER
from authz_v2.services.projections import upload_projection, workspace_projection


def register_core_adapters(resources: ResourceRegistry) -> None:
    for adapter in (
        USER_ADAPTER,
        replace(
            PROJECT_ADAPTER,
            facts_provider=compose_facts(
                PROJECT_ADAPTER.facts_provider, automation_rule_facts
            ),
        ),
        ResourceAdapter(
            "project_allocation_plan",
            lambda db, resource_id: (
                replace(
                    target,
                    context=replace(
                        target.context, resource_type="project_allocation_plan"
                    ),
                )
                if (target := resolve_project(db, resource_id)) is not None
                else None
            ),
            scope_projects,
        ),
        replace(
            PROJECT_UPLOAD_TARGET_ADAPTER,
            resolver=resolve_project_upload_target,
            facts_provider=upload_profile_facts,
        ),
        GRANT_TARGET_ADAPTER,
        *RESOURCE_ADAPTERS,
    ):
        if resources.get(adapter.resource_type) is None:
            resources.register(adapter)


def register_core_choices(choices: ChoiceRegistry) -> None:
    """Register authoritative set projections used by the narrow facade."""
    if choices.get("workspaces") is None:
        choices.register(
            "workspaces",
            Action.AUTHORIZATION_ME_WORKSPACES_VIEW,
            lambda db, _principal, action, grants, _filters: ChoiceListDTO(
                action.value, workspace_projection(db, grants)
            ),
        )
    if choices.get("upload_options") is None:
        choices.register(
            "upload_options",
            Action.AUTHORIZATION_ME_UPLOAD_OPTIONS_VIEW,
            lambda db, principal, action, grants, _filters: ChoiceListDTO(
                action.value, upload_projection(db, principal, grants)
            ),
        )
