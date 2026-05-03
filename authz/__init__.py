"""Central authorization service interfaces."""

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
from authz.types import AuthzActor, AuthzDecision, GrantSource, RelationshipGrant, ResourceRef

__all__ = [
    "AuthzActor",
    "AuthzDecision",
    "GrantSource",
    "RelationshipGrant",
    "ResourceRef",
    "actor_from_user",
    "admin_global_grant",
    "authorize",
    "general_scope_grants",
    "grading_slot_grant",
    "grading_slot_grants",
    "hospital_scope_grant",
    "lab_unit_assignment_grants",
    "upload_profile_grant",
    "upload_profile_grants",
]
