"""Read active Redis bans and durable incidents without revealing credentials."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import os
import time

from flask import current_app
from sqlalchemy import select

from app_init.api_abuse import BAN_INDEX_KEY, BAN_SECONDS, FAILURE_LIMIT, WINDOW_SECONDS, api_abuse_keys
from auth.utils import utcnow
from models import SensitiveOperationAudit, IpLock, User
from project_sync.exceptions import ProjectSyncPermissionDenied
from .geoip import GeoLocation, locate_ip

OPERATION = "api_security_incident"


@dataclass(frozen=True)
class SecurityIncident:
    id: int | None
    ip_address: str
    event: str
    created_at: datetime | None
    blocked_until: datetime | None
    endpoint: str | None
    method: str | None
    geo: GeoLocation

    def to_dict(self):
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat() if self.created_at else None
        data["blocked_until"] = self.blocked_until.isoformat() if self.blocked_until else None
        return data


@dataclass(frozen=True)
class SecurityOverview:
    active_blocks: tuple[SecurityIncident, ...]
    incidents: tuple[SecurityIncident, ...]
    geoip_configured: bool
    generated_at: datetime
    mitigations: tuple[tuple[str, str], ...]
    account_locks: tuple[tuple[str, datetime], ...] = ()

    def to_dict(self):
        return {"active_blocks": [row.to_dict() for row in self.active_blocks],
                "incidents": [row.to_dict() for row in self.incidents],
                "geoip_configured": self.geoip_configured, "generated_at": self.generated_at.isoformat(),
                "account_locks": [{"username": name, "locked_until": until.isoformat()} for name, until in self.account_locks],
                "mitigations": [{"control": name, "policy": policy} for name, policy in self.mitigations]}


def record_ip_ban(db, *, ip_address: str, endpoint: str, method: str):
    row = SensitiveOperationAudit(operation_type=OPERATION, status="ip_banned", ip_address=ip_address)
    row.set_request_details({"endpoint": endpoint, "method": method, "reason": "repeated_api_denials"})
    row.set_result_details({"failure_limit": FAILURE_LIMIT, "window_seconds": WINDOW_SECONDS,
                            "ban_seconds": BAN_SECONDS, "blocked_until": (utcnow() + timedelta(seconds=BAN_SECONDS)).isoformat()})
    db.add(row)


def security_overview(db, *, admin, backend) -> SecurityOverview:
    if not admin or not admin.has_role("admin"):
        raise ProjectSyncPermissionDenied("Only administrators may review security incidents.")
    now = utcnow()
    database_path = current_app.config.get("GEOIP_DATABASE_PATH") or os.getenv("GEOIP_DATABASE_PATH")
    ips = backend.zrevrangebyscore(BAN_INDEX_KEY, "+inf", time.time(), start=0, num=100)
    active = []
    for raw in ips:
        ip = raw.decode() if isinstance(raw, bytes) else raw
        remaining = backend.ttl(api_abuse_keys(ip)[1])
        if remaining > 0:
            active.append(SecurityIncident(None, ip, "ip_banned", None,
                                           now + timedelta(seconds=remaining), None, None,
                                           locate_ip(ip, database_path=database_path)))
    rows = db.execute(select(SensitiveOperationAudit).where(
        SensitiveOperationAudit.operation_type == OPERATION,
        SensitiveOperationAudit.created_at >= now - timedelta(days=31),
    ).order_by(SensitiveOperationAudit.id.desc()).limit(100)).scalars().all()
    password_locks = db.execute(select(IpLock).where(IpLock.locked_until > now)
                               .order_by(IpLock.locked_until.desc()).limit(100)).scalars().all()
    for lock in password_locks:
        active.append(SecurityIncident(None, lock.ip_address, "password_ip_locked", None,
                                       lock.locked_until, None, None,
                                       locate_ip(lock.ip_address, database_path=database_path)))
    account_locks = tuple((name, until) for name, until in db.execute(
        select(User.username, User.is_locked_until).where(User.is_locked_until > now)
        .order_by(User.is_locked_until.desc()).limit(100)
    ).all())
    incidents = []
    for row in rows:
        details, result = row.get_request_details() or {}, row.get_result_details() or {}
        until = datetime.fromisoformat(result["blocked_until"]) if result.get("blocked_until") else None
        incidents.append(SecurityIncident(row.id, row.ip_address or "unknown", row.status, row.created_at, until,
                                          details.get("endpoint"), details.get("method"),
                                          locate_ip(row.ip_address or "unknown", database_path=database_path)))
    enabled = current_app.config.get("API_ABUSE_GUARD_ENABLED", not current_app.testing)
    mitigations = (
        ("API source-IP guard", f"{'Enabled' if enabled else 'Disabled'}: {FAILURE_LIMIT} API 401/403/404 responses in {WINDOW_SECONDS // 60} minutes block the source for {BAN_SECONDS // 3600} hours. Redis failure closes API access."),
        ("Password lockout", "5 failed attempts: account window 30 minutes; IP window 10 minutes; lockout 4 hours. Failed reauthentication also counts."),
        ("Login throttling", "10 attempts/minute/account and 20/minute/source IP. CAPTCHA required for every platform."),
        ("Sync access", "Revalidate active grant, user, project, lab and PII scope on every request; record access and reject unaudited sync responses."),
        ("Saved exports", "Downloads require their original grant and full recorded lab/PII scope. Legacy files without scope metadata are rejected."),
        ("Token invalidation", "Expired/revoked access and refresh tokens rejected; refresh tokens rotate; blocked-device refresh revocations persist."),
        ("CSP migration", "Script unsafe-inline remains enabled pending template/event-handler migration; this control is incomplete."),
    )
    return SecurityOverview(tuple(active), tuple(incidents), bool(database_path), now, mitigations, account_locks)
