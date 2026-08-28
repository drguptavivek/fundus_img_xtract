"""Principal, session, grant, relationship, and evaluation fact contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .resources import ResourceContextDTO, ScopeDTO, ScopeSetDTO
from .roles import Role


class SessionChannel(StrEnum):
    WEB = "web"
    MOBILE = "mobile"
    SIGNED = "signed"
    AUTOMATION = "automation"
    PUBLIC = "public"


class GrantSource(StrEnum):
    AUTHORIZATION_GRANT = "authorization_grant"
    UPLOAD_PROFILE = "upload_profile"
    GRADING_SLOT = "grading_slot"
    PROJECT_ALLOCATION = "project_allocation"
    OWNERSHIP = "ownership"
    PARTICIPATION = "participation"
    NOTIFICATION_RECIPIENT = "notification_recipient"
    PEER = "peer"
    SIGNED_CREDENTIAL = "signed_credential"
    AUTOMATION_RULE = "automation_rule"
    PUBLIC = "public"


@dataclass(frozen=True)
class SessionContextDTO:
    request_id: str
    channel: SessionChannel
    evaluated_at: datetime
    credential_id: str | None = None
    credential_proof: str | None = field(default=None, repr=False, compare=False)
    session_id: str | None = None
    automation_rule_id: int | None = None


@dataclass(frozen=True)
class PrincipalDTO:
    user_id: int | None
    active: bool
    authenticated: bool
    session: SessionContextDTO | None = None


@dataclass(frozen=True)
class RelationshipEvidenceDTO:
    relationship: GrantSource
    evidence_id: int | str | None
    subject_id: int | None
    object_type: str
    object_id: int | str | None
    active: bool
    scope: ScopeDTO | None = None
    attributes: tuple[tuple[str, bool], ...] = ()

    def attribute(self, name: str) -> bool | None:
        """Return one boolean attribute from this exact relationship row."""
        return dict(self.attributes).get(name)


@dataclass(frozen=True)
class RoleGrantDTO:
    grant_id: int
    role: Role
    scope: ScopeDTO


@dataclass(frozen=True)
class EvaluationFactsDTO:
    principal: PrincipalDTO
    session: SessionContextDTO | None = None
    resource: ResourceContextDTO | None = None
    active_roles: frozenset[Role] = field(default_factory=frozenset)
    role_grants: tuple[RoleGrantDTO, ...] = ()
    grant_sources: frozenset[GrantSource] = field(default_factory=frozenset)
    grant_ids: tuple[int, ...] = ()
    reachable_scopes: ScopeSetDTO = field(default_factory=ScopeSetDTO)
    relationships: tuple[RelationshipEvidenceDTO, ...] = ()
    exact_resource: bool = False
    self_identity: bool = False
    owner_or_participant: bool = False
    credential_valid: bool = False
    upload_profile_matches: bool = False
    target_active: bool = False
    grading_slot_matches: bool = False
    allocation_enforced: bool = False
    allocation_matches: bool = False
    domain_valid: bool = False
    automation_rule_matches: bool = False
    automation_target_matches: bool = False
    break_glass_requested: bool = False

    def scope_reaches_resource(self, *, allow_system: bool) -> bool:
        return bool(
            self.resource
            and self.resource.scope
            and self.reachable_scopes.reaches(
                self.resource.scope, allow_system=allow_system
            )
        )
