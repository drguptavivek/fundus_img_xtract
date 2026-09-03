from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from auth.utils import utcnow
from models import Base


class MobilePasskey(Base):
    """One WebAuthn credential registered by a user on a device."""

    __tablename__ = "mobile_passkeys"
    __table_args__ = (UniqueConstraint("credential_id", name="uq_mobile_passkeys_credential_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # base64url credential id, as the browser reports it
    credential_id: Mapped[str] = mapped_column(String(1024), nullable=False)
    # COSE public key bytes
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    aaguid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transports: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
