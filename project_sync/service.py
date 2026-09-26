"""Grant lifecycle and credential authentication for project data sync.

Lifecycle: request (requester, recent re-auth) -> email confirmation (link
sent to the requester's registered address) -> system-admin approval ->
credential issued once to the requester. Every sync call re-derives the
requester's project role scope, so the grant can never outlive the roles that
justified it.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.mobile_tokens import _token_hash_secret
from auth.utils import utcnow
from authz.project_access import allowed_project_lab_unit_ids
from authz.project_roles import DATA_MANAGER, PII_EXPORTER, PROJECT_PI
from models import Project, SensitiveOperationAudit, User
from utils.log_sanitize import sanitize_log_value

from .dto import (
    GrantRequestResult,
    IssuedSyncCredential,
    ProjectSyncGrantDTO,
    RequestMeta,
    SyncContext,
    SyncGrantRequest,
)
from .exceptions import (
    ProjectSyncAuthError,
    ProjectSyncConflict,
    ProjectSyncDisabled,
    ProjectSyncNotFound,
    ProjectSyncPermissionDenied,
    ProjectSyncValidationError,
)
from .models import (
    OPEN_GRANT_STATUSES,
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_PENDING_APPROVAL,
    STATUS_PENDING_EMAIL,
    STATUS_REJECTED,
    STATUS_REVOKED,
    ProjectSyncGrant,
)

logger = logging.getLogger("project_sync")

SYNC_ROLES = frozenset({PROJECT_PI, DATA_MANAGER})
PII_ROLES = frozenset({PROJECT_PI, PII_EXPORTER})
CREDENTIAL_PREFIX = "pds_"
MAX_PURPOSE_LENGTH = 2000
MAX_NOTE_LENGTH = 2000
LAST_USED_WRITE_INTERVAL = timedelta(minutes=1)


# ---------------------------------------------------------------------------
# Server switch and eligibility
# ---------------------------------------------------------------------------


def sync_enabled() -> bool:
    return bool(current_app.config.get("PROJECT_SYNC_ENABLED", False))


def require_sync_enabled() -> None:
    if not sync_enabled():
        raise ProjectSyncDisabled()


def eligible_lab_unit_ids(db, user, *, project_id: int) -> frozenset[int]:
    """Labs the user may mirror: exact project_pi/data_manager grants only.

    System administrators are deliberately not implied: a mirror is a personal
    custody arrangement and must rest on an explicit project role.
    """
    return allowed_project_lab_unit_ids(
        db, user, project_id=project_id, roles=SYNC_ROLES, allow_admin=False
    )


def pii_lab_unit_ids(db, user, *, project_id: int) -> frozenset[int]:
    return allowed_project_lab_unit_ids(
        db, user, project_id=project_id, roles=PII_ROLES, allow_admin=False
    )


def eligible_projects(db, user) -> list[dict]:
    """Projects where the user may request a sync, with PII eligibility."""
    from data_authorization.models import ProjectRoleGrant
    from models import Role

    project_ids = db.execute(
        select(ProjectRoleGrant.project_id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(SYNC_ROLES),
        )
        .distinct()
    ).scalars().all()
    if not project_ids:
        return []
    projects = db.execute(
        select(Project).where(Project.id.in_(project_ids), Project.active.is_(True)).order_by(Project.title)
    ).scalars().all()
    result = []
    for project in projects:
        labs = eligible_lab_unit_ids(db, user, project_id=project.id)
        if not labs:
            continue
        result.append(
            {
                "id": project.id,
                "code": project.code,
                "title": project.title,
                "lab_unit_ids": sorted(labs),
                "pii_eligible": bool(pii_lab_unit_ids(db, user, project_id=project.id) & labs),
            }
        )
    return result


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _hash_secret(value: str) -> str:
    return hmac.new(_token_hash_secret(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_email_token(token: str) -> str:
    return _hash_secret("email:" + token.strip())


def hash_credential(credential: str) -> str:
    return _hash_secret("credential:" + credential.strip())


# ---------------------------------------------------------------------------
# DTO / audit helpers
# ---------------------------------------------------------------------------


def _is_usable(grant: ProjectSyncGrant) -> bool:
    return (
        grant.status == STATUS_APPROVED
        and grant.credential_hash is not None
        and grant.expires_at is not None
        and grant.expires_at > utcnow()
    )


def to_dto(grant: ProjectSyncGrant) -> ProjectSyncGrantDTO:
    return ProjectSyncGrantDTO(
        id=grant.id,
        uuid=grant.uuid,
        project_id=grant.project_id,
        project_code=grant.project.code,
        project_title=grant.project.title,
        user_id=grant.user_id,
        username=grant.user.username,
        status=grant.status,
        include_pii=grant.include_pii,
        purpose=grant.purpose,
        email_confirmed_at=grant.email_confirmed_at,
        decided_by_username=grant.decided_by.username if grant.decided_by else None,
        decided_at=grant.decided_at,
        decision_note=grant.decision_note,
        expires_at=grant.expires_at,
        credential_prefix=grant.credential_prefix,
        credential_issued_at=grant.credential_issued_at,
        last_used_at=grant.last_used_at,
        last_used_ip=grant.last_used_ip,
        revoked_at=grant.revoked_at,
        revoke_reason=grant.revoke_reason,
        created_at=grant.created_at,
        is_usable=_is_usable(grant),
    )


def _audit(db, *, user_id: int | None, status: str, grant: ProjectSyncGrant, meta: RequestMeta, **details) -> None:
    row = SensitiveOperationAudit(
        user_id=user_id,
        operation_type="project_data_sync",
        status=status,
        ip_address=(meta.ip_address or None),
        user_agent=(meta.user_agent or "")[:500] or None,
    )
    row.set_request_details(
        {"grant_uuid": grant.uuid, "project_id": grant.project_id, "grant_user_id": grant.user_id, **details}
    )
    db.add(row)
    logger.info(
        "project_sync %s grant=%s project=%s actor=%s",
        sanitize_log_value(status),
        sanitize_log_value(grant.uuid),
        sanitize_log_value(grant.project_id),
        sanitize_log_value(user_id),
    )


def _load_grant(db, grant_id: int, *, lock: bool = False) -> ProjectSyncGrant:
    query = (
        select(ProjectSyncGrant)
        .options(
            selectinload(ProjectSyncGrant.project),
            selectinload(ProjectSyncGrant.user),
            selectinload(ProjectSyncGrant.decided_by),
        )
        .where(ProjectSyncGrant.id == grant_id)
    )
    if lock:
        query = query.with_for_update(of=ProjectSyncGrant)
    grant = db.execute(query).scalar_one_or_none()
    if grant is None:
        raise ProjectSyncNotFound("Sync grant not found.")
    return grant


def _is_admin(user) -> bool:
    return bool(user is not None and getattr(user, "is_active", False) and user.has_role("admin"))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def request_grant(db, *, user, request: SyncGrantRequest, meta: RequestMeta) -> GrantRequestResult:
    require_sync_enabled()
    purpose = (request.purpose or "").strip()
    if len(purpose) < 10:
        raise ProjectSyncValidationError("Describe the purpose of the local copy (at least 10 characters).")
    if len(purpose) > MAX_PURPOSE_LENGTH:
        raise ProjectSyncValidationError(f"Purpose must be at most {MAX_PURPOSE_LENGTH} characters.")
    project = db.get(Project, request.project_id)
    if project is None or not project.active:
        raise ProjectSyncNotFound("Project not found.")
    labs = eligible_lab_unit_ids(db, user, project_id=project.id)
    if not labs:
        raise ProjectSyncPermissionDenied("Only the project PI or a project data manager may request a sync.")
    if request.include_pii and not (pii_lab_unit_ids(db, user, project_id=project.id) & labs):
        raise ProjectSyncPermissionDenied("Identifier-bearing sync requires the project PI or PII exporter role.")

    email = (getattr(user, "email", None) or "").strip()
    if not email:
        raise ProjectSyncValidationError("Your account has no email address; ask an administrator to add one.")

    existing = db.execute(
        select(ProjectSyncGrant.id).where(
            ProjectSyncGrant.project_id == project.id,
            ProjectSyncGrant.user_id == user.id,
            ProjectSyncGrant.status.in_(OPEN_GRANT_STATUSES),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ProjectSyncConflict("You already have an open sync grant for this project; revoke it first.")

    token = secrets.token_urlsafe(32)
    hours = int(current_app.config.get("PROJECT_SYNC_EMAIL_TOKEN_HOURS", 24))
    grant = ProjectSyncGrant(
        project_id=project.id,
        user_id=user.id,
        status=STATUS_PENDING_EMAIL,
        include_pii=bool(request.include_pii),
        purpose=purpose,
        email_token_hash=hash_email_token(token),
        email_token_expires_at=utcnow() + timedelta(hours=hours),
    )
    db.add(grant)
    db.flush()
    grant = _load_grant(db, grant.id)
    _audit(db, user_id=user.id, status="requested", grant=grant, meta=meta,
           include_pii=grant.include_pii, lab_unit_ids=sorted(labs))
    return GrantRequestResult(grant=to_dto(grant), email_token=token, recipient_email=email)


def confirm_email(db, *, user, token: str, meta: RequestMeta) -> ProjectSyncGrantDTO:
    """Consume the emailed token. The signed-in user must own the grant."""
    require_sync_enabled()
    token = (token or "").strip()
    if not token:
        raise ProjectSyncValidationError("Confirmation token is required.")
    grant = db.execute(
        select(ProjectSyncGrant)
        .where(ProjectSyncGrant.email_token_hash == hash_email_token(token))
        .with_for_update()
    ).scalar_one_or_none()
    if (
        grant is None
        or grant.user_id != user.id
        or grant.status != STATUS_PENDING_EMAIL
        or grant.email_token_expires_at is None
        or grant.email_token_expires_at <= utcnow()
    ):
        raise ProjectSyncValidationError("This confirmation link is invalid or has expired.", code="invalid_token")
    grant.status = STATUS_PENDING_APPROVAL
    grant.email_confirmed_at = utcnow()
    grant.email_token_hash = None
    grant.email_token_expires_at = None
    db.flush()
    grant = _load_grant(db, grant.id)
    _audit(db, user_id=user.id, status="email_confirmed", grant=grant, meta=meta)
    return to_dto(grant)


def approve_grant(db, *, admin, grant_id: int, note: str | None, valid_days: int | None, meta: RequestMeta) -> ProjectSyncGrantDTO:
    require_sync_enabled()
    if not _is_admin(admin):
        raise ProjectSyncPermissionDenied("Only a system administrator may approve sync grants.")
    grant = _load_grant(db, grant_id, lock=True)
    if grant.user_id == admin.id:
        raise ProjectSyncPermissionDenied("You cannot approve your own sync grant.")
    if grant.status != STATUS_PENDING_APPROVAL:
        raise ProjectSyncConflict("Only email-confirmed requests awaiting approval can be approved.")
    requester = grant.user
    if requester is None or not requester.is_active:
        raise ProjectSyncConflict("The requester's account is inactive.")
    labs = eligible_lab_unit_ids(db, requester, project_id=grant.project_id)
    if not labs:
        raise ProjectSyncConflict("The requester no longer holds a project PI or data manager role.")
    if grant.include_pii and not (pii_lab_unit_ids(db, requester, project_id=grant.project_id) & labs):
        raise ProjectSyncConflict("The requester no longer holds a role that permits identifier-bearing sync.")
    max_days = int(current_app.config.get("PROJECT_SYNC_GRANT_DAYS", 90))
    days = max_days if valid_days is None else int(valid_days)
    if days < 1 or days > max_days:
        raise ProjectSyncValidationError(f"valid_days must be between 1 and {max_days}.")
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ProjectSyncValidationError(f"Note must be at most {MAX_NOTE_LENGTH} characters.")
    now = utcnow()
    grant.status = STATUS_APPROVED
    grant.decided_by_user_id = admin.id
    grant.decided_at = now
    grant.decision_note = note
    grant.expires_at = now + timedelta(days=days)
    db.flush()
    grant = _load_grant(db, grant.id)
    _audit(db, user_id=admin.id, status="approved", grant=grant, meta=meta,
           include_pii=grant.include_pii, valid_days=days)
    return to_dto(grant)


def reject_grant(db, *, admin, grant_id: int, note: str | None, meta: RequestMeta) -> ProjectSyncGrantDTO:
    if not _is_admin(admin):
        raise ProjectSyncPermissionDenied("Only a system administrator may reject sync grants.")
    grant = _load_grant(db, grant_id, lock=True)
    if grant.status not in {STATUS_PENDING_EMAIL, STATUS_PENDING_APPROVAL}:
        raise ProjectSyncConflict("Only pending requests can be rejected.")
    grant.status = STATUS_REJECTED
    grant.decided_by_user_id = admin.id
    grant.decided_at = utcnow()
    grant.decision_note = ((note or "").strip() or None)
    grant.email_token_hash = None
    grant.email_token_expires_at = None
    db.flush()
    grant = _load_grant(db, grant.id)
    _audit(db, user_id=admin.id, status="rejected", grant=grant, meta=meta)
    return to_dto(grant)


def issue_credential(db, *, user, grant_id: int, meta: RequestMeta) -> IssuedSyncCredential:
    """Mint (or rotate) the desktop credential. Only the grant owner may do this."""
    require_sync_enabled()
    grant = _load_grant(db, grant_id, lock=True)
    if grant.user_id != user.id:
        raise ProjectSyncNotFound("Sync grant not found.")
    if grant.status != STATUS_APPROVED:
        raise ProjectSyncConflict("A credential can only be issued for an approved grant.")
    if grant.expires_at is None or grant.expires_at <= utcnow():
        raise ProjectSyncConflict("This grant has expired; request a new one.")
    if not eligible_lab_unit_ids(db, user, project_id=grant.project_id):
        raise ProjectSyncPermissionDenied("You no longer hold a project PI or data manager role.")
    rotated = grant.credential_hash is not None
    credential = CREDENTIAL_PREFIX + secrets.token_urlsafe(32)
    grant.credential_hash = hash_credential(credential)
    grant.credential_prefix = credential[:12]
    grant.credential_issued_at = utcnow()
    db.flush()
    grant = _load_grant(db, grant.id)
    _audit(db, user_id=user.id, status="credential_rotated" if rotated else "credential_issued", grant=grant, meta=meta)
    return IssuedSyncCredential(grant=to_dto(grant), credential=credential)


def revoke_grant(db, *, actor, grant_id: int, reason: str | None, meta: RequestMeta) -> ProjectSyncGrantDTO:
    """Owner or system admin. Pending requests become cancelled; approved ones revoked."""
    grant = _load_grant(db, grant_id, lock=True)
    is_owner = grant.user_id == actor.id
    if not is_owner and not _is_admin(actor):
        raise ProjectSyncNotFound("Sync grant not found.")
    if grant.status not in OPEN_GRANT_STATUSES:
        raise ProjectSyncConflict("This grant is already closed.")
    now = utcnow()
    grant.status = STATUS_REVOKED if grant.status == STATUS_APPROVED else STATUS_CANCELLED
    grant.credential_hash = None
    grant.email_token_hash = None
    grant.email_token_expires_at = None
    grant.revoked_at = now
    grant.revoked_by_user_id = actor.id
    grant.revoke_reason = ((reason or "").strip() or None)
    db.flush()
    grant = _load_grant(db, grant.id)
    _audit(db, user_id=actor.id, status=grant.status, grant=grant, meta=meta)
    return to_dto(grant)


def list_user_grants(db, *, user) -> list[ProjectSyncGrantDTO]:
    rows = db.execute(
        select(ProjectSyncGrant)
        .options(
            selectinload(ProjectSyncGrant.project),
            selectinload(ProjectSyncGrant.user),
            selectinload(ProjectSyncGrant.decided_by),
        )
        .where(ProjectSyncGrant.user_id == user.id)
        .order_by(ProjectSyncGrant.created_at.desc())
    ).scalars().all()
    return [to_dto(row) for row in rows]


def list_admin_grants(db, *, admin, status: str | None = None) -> list[ProjectSyncGrantDTO]:
    if not _is_admin(admin):
        raise ProjectSyncPermissionDenied("Only a system administrator may review sync grants.")
    query = (
        select(ProjectSyncGrant)
        .options(
            selectinload(ProjectSyncGrant.project),
            selectinload(ProjectSyncGrant.user),
            selectinload(ProjectSyncGrant.decided_by),
        )
        .order_by(ProjectSyncGrant.created_at.desc())
        .limit(500)
    )
    if status:
        query = query.where(ProjectSyncGrant.status == status)
    return [to_dto(row) for row in db.execute(query).scalars().all()]


def admin_recipients(db) -> list[str]:
    from models import Role, UserRole

    return list(
        db.execute(
            select(User.email)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == "admin", User.is_active.is_(True), User.email.is_not(None))
            .distinct()
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Credential authentication (desktop client)
# ---------------------------------------------------------------------------


def authenticate_credential(db, *, credential: str, meta: RequestMeta) -> SyncContext:
    require_sync_enabled()
    credential = (credential or "").strip()
    if not credential.startswith(CREDENTIAL_PREFIX) or len(credential) > 128:
        raise ProjectSyncAuthError()
    grant = db.execute(
        select(ProjectSyncGrant)
        .options(selectinload(ProjectSyncGrant.project), selectinload(ProjectSyncGrant.user))
        .where(ProjectSyncGrant.credential_hash == hash_credential(credential))
    ).scalar_one_or_none()
    now = utcnow()
    if (
        grant is None
        or grant.status != STATUS_APPROVED
        or grant.expires_at is None
        or grant.expires_at <= now
    ):
        raise ProjectSyncAuthError()
    user = grant.user
    if user is None or not user.is_active or grant.project is None or not grant.project.active:
        raise ProjectSyncAuthError()
    labs = eligible_lab_unit_ids(db, user, project_id=grant.project_id)
    if not labs:
        raise ProjectSyncAuthError()
    pii_labs = pii_lab_unit_ids(db, user, project_id=grant.project_id) & labs if grant.include_pii else frozenset()

    new_ip = bool(meta.ip_address) and meta.ip_address != grant.last_used_ip
    if new_ip or grant.last_used_at is None or now - grant.last_used_at >= LAST_USED_WRITE_INTERVAL:
        if new_ip:
            _audit(db, user_id=user.id, status="credential_used_new_ip", grant=grant, meta=meta)
        grant.last_used_at = now
        grant.last_used_ip = (meta.ip_address or None)
        db.flush()

    return SyncContext(
        grant_id=grant.id,
        grant_uuid=grant.uuid,
        user_id=user.id,
        username=user.username,
        project_id=grant.project_id,
        project_code=grant.project.code,
        lab_unit_ids=frozenset(labs),
        pii_lab_unit_ids=frozenset(pii_labs),
        expires_at=grant.expires_at,
    )


def grant_export_lab_unit_ids(db, *, grant_uuid: str, user_id: int, project_id: int) -> frozenset[int]:
    """Labs a queued sync export may include; empty when the grant lapsed.

    Runs inside Celery, so it checks the grant row directly rather than the
    request-time server switch (enforced when the job was enqueued).
    """
    grant = db.execute(
        select(ProjectSyncGrant).where(ProjectSyncGrant.uuid == grant_uuid)
    ).scalar_one_or_none()
    if (
        grant is None
        or grant.user_id != user_id
        or grant.project_id != project_id
        or grant.status != STATUS_APPROVED
        or grant.expires_at is None
        or grant.expires_at <= utcnow()
    ):
        return frozenset()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return frozenset()
    return eligible_lab_unit_ids(db, user, project_id=project_id)
