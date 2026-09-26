"""ORM ownership for project data sync grants."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

STATUS_PENDING_EMAIL = "pending_email"
STATUS_PENDING_APPROVAL = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_REVOKED = "revoked"
STATUS_CANCELLED = "cancelled"

GRANT_STATUSES = (
    STATUS_PENDING_EMAIL,
    STATUS_PENDING_APPROVAL,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_REVOKED,
    STATUS_CANCELLED,
)
OPEN_GRANT_STATUSES = frozenset({STATUS_PENDING_EMAIL, STATUS_PENDING_APPROVAL, STATUS_APPROVED})


class ProjectSyncGrant(Base):
    """One user's permission to mirror one project's data onto a desktop.

    A grant is only usable after three independent gates: the requester proves
    control of their mailbox (``email_confirmed_at``), a system administrator
    approves it (``decided_by_user_id``), and the requester then mints a
    credential that is shown once and stored only as an HMAC. The requester's
    project role grants are re-derived on every sync request, so losing the
    role stops the sync without anyone touching this row.
    """

    __tablename__ = "project_sync_grants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, default=lambda: str(uuid4()))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=STATUS_PENDING_EMAIL, index=True)
    include_pii: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    purpose: Mapped[str] = mapped_column(Text, nullable=False)

    email_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    email_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    credential_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    credential_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    credential_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    decided_by: Mapped["User | None"] = relationship("User", foreign_keys=[decided_by_user_id])
    revoked_by: Mapped["User | None"] = relationship("User", foreign_keys=[revoked_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_email','pending_approval','approved','rejected','revoked','cancelled')",
            name="ck_project_sync_grants_status",
        ),
        Index(
            "uq_project_sync_grants_open",
            "project_id",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('pending_email','pending_approval','approved')"),
        ),
    )
