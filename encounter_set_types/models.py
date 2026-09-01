"""Encounter-set type ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from models import User


class EncounterSetType(Base):
    """Reusable encounter-set metadata and asset contract."""

    __tablename__ = "encounter_set_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: {"fields": []})
    asset_rules_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: default_asset_rules())
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        UniqueConstraint("code", name="uq_encounter_set_types_code"),
        Index("ix_encounter_set_types_active", "active"),
    )


class EncounterSetImportMapperRevision(Base):
    """Versioned CSV-to-EncounterSetType mapping configuration."""

    __tablename__ = "encounter_set_import_mapper_revisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mapper_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    encounter_set_type_id: Mapped[int] = mapped_column(
        ForeignKey("encounter_set_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft", index=True)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_header_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_headers_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    mapping_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cloned_from_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounter_set_import_mapper_revisions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    encounter_set_type: Mapped["EncounterSetType"] = relationship("EncounterSetType")

    __table_args__ = (
        UniqueConstraint("mapper_uuid", "revision", name="uq_encounter_set_import_mapper_revision"),
        CheckConstraint("status IN ('draft', 'finalized', 'retired')", name="ck_encounter_set_import_mapper_status"),
        CheckConstraint("use_count >= 0", name="ck_encounter_set_import_mapper_use_count"),
        Index("ix_encounter_set_import_mapper_type_status", "encounter_set_type_id", "status"),
    )


class EncounterSetImportMapperAudit(Base):
    """Append-only lifecycle audit for import mapper revisions."""

    __tablename__ = "encounter_set_import_mapper_audits"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mapper_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounter_set_import_mapper_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mapper_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def default_asset_rules() -> dict[str, Any]:
    """Default EncounterSetType asset permissions."""
    return {
        "allow_clinical_images": True,
        "min_clinical_images": None,
        "max_clinical_images": None,
        "allow_document_uploads": False,
        "allow_pdf_uploads": False,
        "allow_document_image_uploads": False,
        "max_documents": None,
        "max_pdfs": None,
        "max_document_images": None,
        "allow_report_uploads": False,
        "allow_report_pdfs": False,
        "allow_report_images": False,
        "max_reports": None,
    }
