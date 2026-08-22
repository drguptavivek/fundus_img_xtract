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
    self_grant,
    upload_profile_grant,
    upload_profile_grants,
)
from authz.engine import authorize
from authz.predicates import (
    reachable_hospital_ids,
    reachable_lab_unit_ids,
    scope,
    scope_predicate,
    scope_query,
)
from authz.resolver import ResolvedGrants, resolve_grants
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
    "ResolvedGrants",
    "authorize",
    "general_scope_grants",
    "get_action",
    "grading_slot_grant",
    "grading_slot_grants",
    "hospital_scope_grant",
    "lab_unit_assignment_grants",
    "load_action_registry",
    "reachable_hospital_ids",
    "reachable_lab_unit_ids",
    "resolve_grants",
    "scope",
    "scope_predicate",
    "scope_query",
    "self_grant",
    "upload_profile_grant",
    "upload_profile_grants",
]
