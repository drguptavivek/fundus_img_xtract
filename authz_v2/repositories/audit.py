"""Append-only authorization audit repository."""

from __future__ import annotations

from authz_v2.domain.models import AuthorizationAuditEvent


class AuditRepository:
    def __init__(self, db) -> None:
        self.db = db

    def append(self, event: AuthorizationAuditEvent) -> AuthorizationAuditEvent:
        self.db.add(event)
        self.db.flush()
        return event
