"""Dependency-clean authorization contracts (temporary cutover package)."""

from .core.actions import (
    ACTION_MANIFEST,
    ACTION_MIGRATION_MAP,
    Action,
    action_from_name,
)
from .core.decisions import AuthorizationReceiptDTO, DecisionDTO
from .core.principals import PrincipalDTO, SessionContextDTO
from .core.resources import ResourceContextDTO, ScopeDTO, ScopeSetDTO

__all__ = [
    "ACTION_MANIFEST",
    "ACTION_MIGRATION_MAP",
    "Action",
    "AuthorizationReceiptDTO",
    "DecisionDTO",
    "PrincipalDTO",
    "ResourceContextDTO",
    "ScopeDTO",
    "ScopeSetDTO",
    "SessionContextDTO",
    "action_from_name",
]
