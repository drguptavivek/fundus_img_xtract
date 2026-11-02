"""Privacy-safe sync request audit and bounded admin review queries."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import ipaddress

from sqlalchemy import JSON, cast, func, select

from auth.utils import utcnow
from models import Project, SensitiveOperationAudit, User
from .dto import SyncContext
from .exceptions import ProjectSyncPermissionDenied, ProjectSyncValidationError

REQUEST_OPERATION = "project_sync_request"
OPERATIONS = (REQUEST_OPERATION, "project_data_sync")
PAGE_SIZE = 50


@dataclass(frozen=True)
class AuditFilter:
    since: datetime
    until: datetime
    username: str = ""
    project_id: int | None = None
    ip_address: str = ""
    before_id: int | None = None

    @classmethod
    def parse(cls, *, since=None, until=None, username="", project_id=None, ip_address="", before_id=None):
        def timestamp(value, default):
            if not value:
                return default
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
            except ValueError:
                raise ProjectSyncValidationError("Dates must use ISO 8601 format.") from None

        now = utcnow()
        start, end = timestamp(since, now - timedelta(days=7)), timestamp(until, now)
        if start >= end or end - start > timedelta(days=31):
            raise ProjectSyncValidationError("Choose an increasing time range of at most 31 days.")
        try:
            project = int(project_id) if project_id else None
            cursor = int(before_id) if before_id else None
            ip = str(ipaddress.ip_address(ip_address.strip())) if ip_address else ""
            if (project is not None and project < 1) or (cursor is not None and cursor < 1):
                raise ValueError
        except (ValueError, TypeError):
            raise ProjectSyncValidationError("Project, cursor, or IP address is invalid.") from None
        return cls(start, end, str(username or "").strip()[:150], project, ip, cursor)


@dataclass(frozen=True)
class AuditEvent:
    id: int
    created_at: datetime
    username: str | None
    project_id: int | None
    project_code: str | None
    ip_address: str | None
    event: str
    endpoint: str | None
    method: str | None
    http_status: int | None
    grant_uuid: str | None
    response_bytes: int | None
    duration_ms: int | None
    user_agent: str | None

    def to_dict(self):
        return {**asdict(self), "created_at": self.created_at.isoformat()}


@dataclass(frozen=True)
class AuditPage:
    events: tuple[AuditEvent, ...]
    next_before_id: int | None
    total_events: int
    filters: AuditFilter

    def to_dict(self):
        return {"events": [row.to_dict() for row in self.events], "next_before_id": self.next_before_id,
                "total_events": self.total_events, "since": self.filters.since.isoformat(), "until": self.filters.until.isoformat()}


def record_sync_request(db, *, context: SyncContext | None, ip_address: str,
                        user_agent: str, endpoint: str, method: str, http_status: int,
                        response_bytes: int | None, duration_ms: int) -> None:
    row = SensitiveOperationAudit(
        user_id=context.user_id if context else None, operation_type=REQUEST_OPERATION,
        status="served" if 200 <= http_status < 400 else "denied",
        ip_address=ip_address, user_agent=user_agent[:500] or None,
    )
    row.set_request_details({
        "project_id": context.project_id if context else None,
        "grant_uuid": context.grant_uuid if context else None,
        "endpoint": endpoint, "method": method,
    })
    row.set_result_details({"http_status": http_status, "response_bytes": response_bytes, "duration_ms": duration_ms})
    db.add(row)


def review_sync_audit(db, *, admin, filters: AuditFilter) -> AuditPage:
    if not admin or not admin.has_role("admin"):
        raise ProjectSyncPermissionDenied("Only administrators may review sync activity.")
    details = cast(SensitiveOperationAudit.request_details, JSON)
    project_key = details["project_id"].as_integer()
    query = (select(SensitiveOperationAudit, User.username, Project.code)
             .outerjoin(User, User.id == SensitiveOperationAudit.user_id)
             .outerjoin(Project, Project.id == project_key)
             .where(SensitiveOperationAudit.operation_type.in_(OPERATIONS),
                    SensitiveOperationAudit.created_at >= filters.since,
                    SensitiveOperationAudit.created_at <= filters.until))
    if filters.username:
        query = query.where(func.lower(User.username) == filters.username.lower())
    if filters.project_id:
        query = query.where(project_key == filters.project_id)
    if filters.ip_address:
        query = query.where(SensitiveOperationAudit.ip_address == filters.ip_address)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    if filters.before_id:
        query = query.where(SensitiveOperationAudit.id < filters.before_id)
    rows = db.execute(query.order_by(SensitiveOperationAudit.id.desc()).limit(PAGE_SIZE + 1)).all()
    events = []
    for row, username, project_code in rows[:PAGE_SIZE]:
        request_data, result = row.get_request_details() or {}, row.get_result_details() or {}
        events.append(AuditEvent(row.id, row.created_at, username, request_data.get("project_id"), project_code,
                                 row.ip_address, row.status, request_data.get("endpoint"), request_data.get("method"),
                                 result.get("http_status"), request_data.get("grant_uuid"), result.get("response_bytes"),
                                 result.get("duration_ms"), row.user_agent))
    return AuditPage(tuple(events), events[-1].id if len(rows) > PAGE_SIZE else None, total, filters)
