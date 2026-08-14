"""Public interface for the transport-neutral central authorization engine.

Callers resolve persisted relationships in their domain module, convert them
to these value objects, and ask the pure engine for a decision. This package
does not query application tables or serve protected resources.
"""

from authz.adapters import (
    actor_from_user,
    admin_global_grant,
    general_scope_grants,
    grading_slot_grant,
    grading_slot_grants,
    hospital_scope_grant,
    lab_unit_assignment_grants,
    upload_profile_grant,
    upload_profile_grants,
)
from authz.engine import authorize
from authz.registry import ActionDefinition, ActionRegistryError, get_action, load_action_registry
from authz.types import AuthzActor, AuthzDecision, GrantSource, RelationshipGrant, ResourceRef

__all__ = [
    "ActionDefinition",
    "ActionRegistryError",
    "AuthzActor",
    "AuthzDecision",
    "GrantSource",
    "RelationshipGrant",
    "ResourceRef",
    "actor_from_user",
    "admin_global_grant",
    "authorize",
    "general_scope_grants",
    "get_action",
    "grading_slot_grant",
    "grading_slot_grants",
    "hospital_scope_grant",
    "lab_unit_assignment_grants",
    "load_action_registry",
    "upload_profile_grant",
    "upload_profile_grants",
]
