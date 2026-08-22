"""Project-owned configuration models."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from models import LabUnit, Project


class ProjectLabUnit(Base):
    """Explicit lab-unit boundary for every project-owned workflow."""

    __tablename__ = "project_lab_units"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lab_unit_id: Mapped[int] = mapped_column(
        ForeignKey("lab_units.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(
        default=True, server_default="true", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship("Project")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")

    __table_args__ = (
        UniqueConstraint("project_id", "lab_unit_id", name="uq_project_lab_units_project_lab"),
        Index("ix_project_lab_units_project_active", "project_id", "active"),
    )
