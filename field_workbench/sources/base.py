"""The contract each upstream fetch adapter implements.

Remidio and IITK track fetch state in genuinely different ways - Remidio uses
Job/JobItem rows, IITK a lease on its config row - so the field routes talk to
this contract rather than branching on source inline.

Each adapter module provides:

    is_configured(db, *, project_id) -> bool
    fetch_status(db, *, project_id, scope) -> FetchStatusDTO
    queue_fetch(db, *, project_id, user, scope, remote_addr) -> FetchStatusDTO
    retry_fetch(db, *, project_id, user, scope, remote_addr) -> FetchStatusDTO

``queue_fetch`` must be coalescing: when a fetch is already in flight it returns
that fetch's status instead of starting another. That guard, not the per-user
rate limit, is what actually protects the upstream provider, because it holds
however many field users tap at once.
"""
from __future__ import annotations

from typing import Protocol

from ..dto import FetchStatusDTO


class FieldSourceAdapter(Protocol):
    def is_configured(self, db, *, project_id: int) -> bool: ...

    def fetch_status(self, db, *, project_id: int, scope) -> FetchStatusDTO: ...

    def queue_fetch(self, db, *, project_id: int, user, scope, remote_addr: str | None) -> FetchStatusDTO: ...

    def retry_fetch(self, db, *, project_id: int, user, scope, remote_addr: str | None) -> FetchStatusDTO: ...
