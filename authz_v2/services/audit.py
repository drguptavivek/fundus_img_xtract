"""Privacy-limited durable authorization audit persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping

from authz_v2.core.decisions import AuthorizationReceiptDTO
from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import ResourceContextDTO
from authz_v2.domain.models import AuthorizationAuditEvent
from authz_v2.repositories.audit import AuditRepository

ALLOWED_DETAIL_KEYS = frozenset(
    {"grant_id", "changed_fields", "policy_id", "result_count"}
)
ALLOWED_CHANGED_FIELDS = frozenset(
    {"active", "description", "role", "scope", "user_id"}
)


def _sanitize_details(details: Mapping[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in details.items():
        if key not in ALLOWED_DETAIL_KEYS:
            continue
        if key in {"grant_id", "policy_id", "result_count"}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid audit detail: {key}")
            sanitized[key] = value
            continue
        if isinstance(value, Mapping):
            fields = value.keys()
        elif isinstance(value, (list, tuple, set, frozenset)):
            fields = value
        else:
            raise TypeError("invalid audit detail: changed_fields")
        if any(not isinstance(field, str) for field in fields):
            raise ValueError("invalid audit detail: changed_fields")
        normalized = sorted(set(fields))
        if not set(normalized) <= ALLOWED_CHANGED_FIELDS:
            raise ValueError("invalid audit detail: changed_fields")
        sanitized[key] = normalized
    return sanitized


class AuthorizationAuditService:
    """Append audit rows containing only approved internal references."""

    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    def record_allowed(
        self,
        *,
        event: str,
        principal: PrincipalDTO,
        receipt: AuthorizationReceiptDTO,
        resource: ResourceContextDTO | None = None,
        details: Mapping[str, object] | None = None,
    ) -> AuthorizationAuditEvent:
        sanitized = _sanitize_details(details or {})
        row = AuthorizationAuditEvent(
            event=event,
            action=receipt.action,
            outcome="allow",
            actor_id=principal.user_id,
            session_kind=principal.session.channel.value
            if principal.session
            else "unknown",
            policy_path=receipt.policy_path,
            break_glass=receipt.break_glass,
            request_id=receipt.request_id,
            resource_type=resource.resource_type if resource else receipt.resource_type,
            resource_id=(
                str(resource.resource_id if resource else receipt.resource_id)
                if (resource.resource_id if resource else receipt.resource_id)
                is not None
                else None
            ),
            scope_type=resource.scope.scope_type.value
            if resource and resource.scope
            else None,
            scope_id=str(resource.scope.scope_id)
            if resource and resource.scope and resource.scope.scope_id is not None
            else None,
            detail_json=json.dumps(sanitized, sort_keys=True) if sanitized else None,
        )
        return self.repository.append(row)

    def record_denied(
        self,
        *,
        event: str,
        action: str,
        principal: PrincipalDTO,
    ) -> AuthorizationAuditEvent:
        # Attacker-supplied resource identifiers are deliberately omitted.
        row = AuthorizationAuditEvent(
            event=event,
            action=action,
            outcome="deny",
            actor_id=principal.user_id,
            session_kind=principal.session.channel.value
            if principal.session
            else "unknown",
            request_id=principal.session.request_id if principal.session else None,
            break_glass=False,
        )
        return self.repository.append(row)
