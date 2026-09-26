"""DTOs crossing the project sync service boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(frozen=True)
class ProjectSyncGrantDTO:
    id: int
    uuid: str
    project_id: int
    project_code: str
    project_title: str
    user_id: int
    username: str
    status: str
    include_pii: bool
    purpose: str
    email_confirmed_at: datetime | None
    decided_by_username: str | None
    decided_at: datetime | None
    decision_note: str | None
    expires_at: datetime | None
    credential_prefix: str | None
    credential_issued_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None
    revoked_at: datetime | None
    revoke_reason: str | None
    created_at: datetime
    is_usable: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "uuid": self.uuid,
            "project": {"id": self.project_id, "code": self.project_code, "title": self.project_title},
            "user": {"id": self.user_id, "username": self.username},
            "status": self.status,
            "include_pii": self.include_pii,
            "purpose": self.purpose,
            "email_confirmed_at": _iso(self.email_confirmed_at),
            "decided_by": self.decided_by_username,
            "decided_at": _iso(self.decided_at),
            "decision_note": self.decision_note,
            "expires_at": _iso(self.expires_at),
            "credential_prefix": self.credential_prefix,
            "credential_issued_at": _iso(self.credential_issued_at),
            "last_used_at": _iso(self.last_used_at),
            "last_used_ip": self.last_used_ip,
            "revoked_at": _iso(self.revoked_at),
            "revoke_reason": self.revoke_reason,
            "created_at": _iso(self.created_at),
            "is_usable": self.is_usable,
        }


@dataclass(frozen=True)
class SyncGrantRequest:
    project_id: int
    purpose: str
    include_pii: bool = False


@dataclass(frozen=True)
class GrantRequestResult:
    """``email_token`` is plaintext and must only be delivered by email."""

    grant: ProjectSyncGrantDTO
    email_token: str
    recipient_email: str


@dataclass(frozen=True)
class IssuedSyncCredential:
    """The plaintext credential is returned once and never stored."""

    grant: ProjectSyncGrantDTO
    credential: str


@dataclass(frozen=True)
class RequestMeta:
    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class SyncContext:
    """Everything a sync request may touch, re-derived on every call."""

    grant_id: int
    grant_uuid: str
    user_id: int
    username: str
    project_id: int
    project_code: str
    lab_unit_ids: frozenset[int]
    pii_lab_unit_ids: frozenset[int] = field(default_factory=frozenset)
    expires_at: datetime | None = None

    def allows_lab(self, lab_unit_id: int | None) -> bool:
        return lab_unit_id is not None and lab_unit_id in self.lab_unit_ids

    def allows_pii(self, lab_unit_id: int | None) -> bool:
        return lab_unit_id is not None and lab_unit_id in self.pii_lab_unit_ids
