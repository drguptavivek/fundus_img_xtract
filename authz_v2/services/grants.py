"""Authorized grant lifecycle operations with delegation containment."""

from __future__ import annotations

from auth.utils import utcnow
from authz_v2.core.actions import Action
from authz_v2.core.decisions import AuthorizationReceiptDTO
from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import Role, may_delegate
from authz_v2.domain.grants import (
    DESCRIPTION_UNSET,
    GrantCreateDTO,
    GrantUpdateDTO,
    normalize_description,
    validate_grant_target,
)
from authz_v2.domain.models import AuthorizationGrant
from authz_v2.repositories.grants import GrantRepository
from authz_v2.resources.grants import GrantTargetRef
from authz_v2.services.audit import AuthorizationAuditService
from authz_v2.services.decision import AuthorizationDecisionService


class GrantMutationService:
    """Create, reactivate, or update grants without widening actor authority."""

    def __init__(
        self,
        repository: GrantRepository,
        decision_service: AuthorizationDecisionService,
        audit_service: AuthorizationAuditService,
    ) -> None:
        self.repository = repository
        self.decision_service = decision_service
        self.audit_service = audit_service

    def create(
        self, actor: PrincipalDTO, request: GrantCreateDTO
    ) -> AuthorizationGrant:
        actor = self.decision_service.authoritative_principal(actor)
        actor_id = self._actor_id(actor)
        if request.user_id == actor_id:
            raise PermissionError("not_authorized")
        scope = self.repository.resolve_scope(request.scope)
        if scope is None:
            raise ValueError("authorization grant has an unresolved scope")
        validate_grant_target(request.role, scope)
        require = getattr(
            self.decision_service,
            "require_audited",
            self.decision_service.require,
        )
        kwargs = (
            {"audit_service": self.audit_service}
            if hasattr(self.decision_service, "require_audited")
            else {}
        )
        receipt = require(
            self.repository.db,
            actor,
            Action.AUTHORIZATION_GRANTS_MANAGE,
            GrantTargetRef(request.user_id, scope.scope_type, scope.scope_id),
            **kwargs,
        )
        self._require_delegation(actor_id, request.role, scope)
        role_id = self.repository.role_id(request.role)
        if role_id is None:
            raise ValueError(f"unknown stored role: {request.role.value}")
        existing = self.repository.find_historical(
            user_id=request.user_id,
            role_id=role_id,
            scope=scope,
        )
        now = utcnow()
        if existing is not None:
            existing.active = True
            existing.description = normalize_description(request.description)
            existing.updated_by_user_id = actor_id
            existing.deactivated_by_user_id = None
            existing.deactivated_at = None
            existing.updated_at = now
            self.repository.db.flush()
            self._audit(
                event="grant_reactivate",
                actor=actor,
                receipt=receipt,
                grant=existing,
                scope=scope,
                changed_fields=("active", "description"),
            )
            return existing
        grant = AuthorizationGrant(
            user_id=request.user_id,
            role_id=role_id,
            scope_type=scope.scope_type.value,
            hospital_id=scope.scope_id
            if scope.scope_type.value == "hospital"
            else None,
            lab_unit_id=scope.scope_id
            if scope.scope_type.value == "lab_unit"
            else None,
            project_id=scope.scope_id if scope.scope_type.value == "project" else None,
            project_lab_unit_id=(
                scope.scope_id if scope.scope_type.value == "project_lab_unit" else None
            ),
            description=normalize_description(request.description),
            active=True,
            created_by_user_id=actor_id,
            updated_by_user_id=actor_id,
            created_at=now,
            updated_at=now,
        )
        grant = self.repository.add(grant)
        self._audit(
            event="grant_create",
            actor=actor,
            receipt=receipt,
            grant=grant,
            scope=scope,
            changed_fields=("active", "description", "role", "scope", "user_id"),
        )
        return grant

    def update(
        self,
        actor: PrincipalDTO,
        grant_id: int,
        request: GrantUpdateDTO,
    ) -> AuthorizationGrant:
        actor = self.decision_service.authoritative_principal(actor)
        actor_id = self._actor_id(actor)
        grant = self.repository.get_for_update(grant_id)
        if grant is None:
            raise LookupError("authorization grant not found")
        if grant.user_id == actor_id:
            raise PermissionError("not_authorized")
        role = self.repository.role_for(grant.role_id)
        if role is None:
            raise ValueError("authorization grant has an unknown role")
        scope = self.repository.scope_for(grant)
        if scope is None:
            raise ValueError("authorization grant has unresolved scope")
        require = getattr(
            self.decision_service,
            "require_audited",
            self.decision_service.require,
        )
        kwargs = (
            {"audit_service": self.audit_service}
            if hasattr(self.decision_service, "require_audited")
            else {}
        )
        receipt = require(
            self.repository.db,
            actor,
            Action.AUTHORIZATION_GRANTS_MANAGE,
            GrantTargetRef(grant.user_id, scope.scope_type, scope.scope_id),
            **kwargs,
        )
        self._require_delegation(actor_id, role, scope)
        changed_fields: list[str] = []
        if request.description is not DESCRIPTION_UNSET:
            grant.description = normalize_description(request.description)
            changed_fields.append("description")
        if request.active is not None and request.active != grant.active:
            grant.active = request.active
            changed_fields.append("active")
            if request.active:
                grant.deactivated_at = None
                grant.deactivated_by_user_id = None
            else:
                grant.deactivated_at = utcnow()
                grant.deactivated_by_user_id = actor_id
        if not changed_fields:
            raise ValueError("grant update contains no changes")
        grant.updated_by_user_id = actor_id
        grant.updated_at = utcnow()
        self.repository.db.flush()
        self._audit(
            event="grant_update",
            actor=actor,
            receipt=receipt,
            grant=grant,
            scope=scope,
            changed_fields=tuple(changed_fields),
        )
        return grant

    def _audit(
        self,
        *,
        event: str,
        actor: PrincipalDTO,
        receipt: AuthorizationReceiptDTO,
        grant: AuthorizationGrant,
        scope: ScopeDTO,
        changed_fields: tuple[str, ...],
    ) -> None:
        self.audit_service.record_allowed(
            event=event,
            principal=actor,
            receipt=receipt,
            resource=ResourceContextDTO(
                "authorization_grant", grant.id, scope, resolved=True
            ),
            details={
                "grant_id": grant.id,
                "changed_fields": changed_fields,
            },
        )

    def _require_delegation(self, actor_id: int, role: Role, scope: ScopeDTO) -> None:
        actor_grants = self.repository.grants_for(actor_id)
        allowed = any(
            may_delegate(grant.role, role)
            and grant.scope.contains(scope, allow_system=grant.role is Role.ADMIN)
            for grant in actor_grants
        )
        if not allowed:
            raise PermissionError("not_authorized")

    @staticmethod
    def _actor_id(actor: PrincipalDTO) -> int:
        if actor.user_id is None or not actor.active or not actor.authenticated:
            raise PermissionError("not_authorized")
        return actor.user_id
