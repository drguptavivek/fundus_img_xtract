"""ORM ownership for enrolled mobile and desktop client devices."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

DEVICE_STATUSES = ("pending", "approved", "blocked")
DEVICE_KINDS = ("personal", "shared")
DEVICE_PLATFORMS = ("android", "ios", "windows", "macos", "web")


class MobileDevice(Base):
    """One enrolled client device for one user.

    ``device_id`` is client-supplied, so it only becomes trustworthy once an
    administrator has enrolled it here. Login refuses to mint tokens for any
    device without an ``approved`` row, and
    :func:`services.mobile.auth_sessions.validate_access_session` re-checks the
    status on every request, so blocking a device kills its live sessions at the
    next call rather than at token expiry.

    The name is historical: Windows and macOS desktop builds are first-class
    clients of the same bearer-token API and enrol through the same gate.
    """

    __tablename__ = "mobile_devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending", index=True)
    device_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="personal", server_default="personal")
    platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    enrolled_by: Mapped["User | None"] = relationship("User", foreign_keys=[enrolled_by_user_id])

    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_mobile_devices_user_device"),
        CheckConstraint("status IN ('pending','approved','blocked')", name="ck_mobile_devices_status"),
        CheckConstraint("device_kind IN ('personal','shared')", name="ck_mobile_devices_kind"),
        CheckConstraint(
            "platform IS NULL OR platform IN ('android','ios','windows','macos','web')",
            name="ck_mobile_devices_platform",
        ),
        Index("ix_mobile_devices_user_status", "user_id", "status"),
    )


class MobileDeviceEnrolmentCode(Base):
    """A short-lived, single-use code that authorises one device enrolment.

    The code is stored hashed; the plaintext is shown to the administrator once
    and never persisted. Binding the code to ``user_id`` means a leaked code
    cannot enrol a device against a different account.
    """

    __tablename__ = "mobile_device_enrolment_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    device_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="personal", server_default="personal")
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    issued_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    issued_by: Mapped["User | None"] = relationship("User", foreign_keys=[issued_by_user_id])

    __table_args__ = (
        CheckConstraint("device_kind IN ('personal','shared')", name="ck_mobile_device_codes_kind"),
        Index("ix_mobile_device_codes_user_used", "user_id", "used_at"),
    )
