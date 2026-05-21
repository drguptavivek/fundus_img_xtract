"""Encounter-set type ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from models import Disease, Project, User


class EncounterSetType(Base):
    """Project-scoped encounter-set metadata contract and grading target."""

    __tablename__ = "encounter_set_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_scheme_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    metadata_schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=lambda: {"fields": []})
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    project: Mapped["Project"] = relationship("Project", back_populates="encounter_set_types")
    target_scheme: Mapped["Disease"] = relationship("Disease")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_encounter_set_types_project_code"),
        Index("ix_encounter_set_types_project_active", "project_id", "active"),
        Index("ix_encounter_set_types_target_scheme_id", "target_scheme_id"),
    )
