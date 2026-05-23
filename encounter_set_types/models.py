"""Encounter-set type ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from models import Disease, User


class EncounterSetType(Base):
    """Reusable encounter-set metadata contract and grading targets."""

    __tablename__ = "encounter_set_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    encounter_grading_scheme_id: Mapped[int | None] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=True, index=True)
    metadata_schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: {"fields": []})
    asset_rules_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: default_asset_rules())
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    encounter_grading_scheme: Mapped["Disease | None"] = relationship("Disease", foreign_keys=[encounter_grading_scheme_id])
    image_grading_schemes: Mapped[list["EncounterSetTypeImageGradingScheme"]] = relationship(
        "EncounterSetTypeImageGradingScheme",
        back_populates="encounter_set_type",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="EncounterSetTypeImageGradingScheme.display_order",
    )
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        UniqueConstraint("code", name="uq_encounter_set_types_code"),
        Index("ix_encounter_set_types_active", "active"),
        Index("ix_encounter_set_types_encounter_grading_scheme_id", "encounter_grading_scheme_id"),
    )


class EncounterSetTypeImageGradingScheme(Base):
    """Image-level grading scheme allow-list for one EncounterSetType."""

    __tablename__ = "encounter_set_type_image_grading_schemes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    encounter_set_type_id: Mapped[int] = mapped_column(ForeignKey("encounter_set_types.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, server_default="false")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    encounter_set_type: Mapped["EncounterSetType"] = relationship("EncounterSetType", back_populates="image_grading_schemes")
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("encounter_set_type_id", "disease_id", name="uq_est_image_grading_scheme"),
        Index("ix_est_image_grading_scheme_type_active", "encounter_set_type_id", "active"),
        Index("ix_est_image_grading_scheme_default", "encounter_set_type_id", "is_default"),
    )


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
