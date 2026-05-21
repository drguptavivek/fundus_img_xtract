"""Standalone upload metadata field master models."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from models import User


class UploadMetadataFieldDefinition(Base):
    """Reusable metadata field template available to any upload workflow."""

    __tablename__ = "upload_metadata_field_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    sctid: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)
    selection_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    options_json: Mapped[list[dict[str, str]] | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_at_upload_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    required_for_verification_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    visible_to_grader_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    is_pii_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        UniqueConstraint("key", name="uq_upload_metadata_field_definitions_key"),
        Index("ix_upload_metadata_field_definitions_scope_active", "scope", "active"),
    )
