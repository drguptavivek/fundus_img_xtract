"""ORM persistence for project grading allocation."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from encounter_set_types.models import EncounterSetType
    from models import Disease, LabUnit, Project, User


class ProjectGradingAllocationPolicy(Base):
    """Explicit activation boundary for project-scoped allocation enforcement."""

    __tablename__ = "project_grading_allocation_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    enforcement_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship("Project")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])


class ProjectGraderAllocation(Base):
    """One user/capacity assignment to a semantic grading target in a project."""

    __tablename__ = "project_grader_allocations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lab_unit_id: Mapped[int] = mapped_column(
        ForeignKey("lab_units.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    disease_id: Mapped[int | None] = mapped_column(
        ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    encounter_set_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounter_set_types.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    capacity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship("Project")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")
    disease: Mapped["Disease | None"] = relationship("Disease")
    encounter_set_type: Mapped["EncounterSetType | None"] = relationship("EncounterSetType")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "scope IN ('disease_image','disease_encounter','encounter_set_unified')",
            name="ck_project_grader_allocation_scope",
        ),
        CheckConstraint(
            "capacity IN ('resident','arbitrator')",
            name="ck_project_grader_allocation_capacity",
        ),
        CheckConstraint(
            "(scope = 'disease_image' AND disease_id IS NOT NULL AND encounter_set_type_id IS NULL) OR "
            "(scope = 'disease_encounter' AND disease_id IS NOT NULL AND encounter_set_type_id IS NOT NULL) OR "
            "(scope = 'encounter_set_unified' AND disease_id IS NULL AND encounter_set_type_id IS NOT NULL)",
            name="ck_project_grader_allocation_target_shape",
        ),
        Index(
            "uq_project_grader_allocation_image",
            "project_id", "user_id", "lab_unit_id", "disease_id", "capacity",
            unique=True,
            postgresql_where=text("scope = 'disease_image'"),
        ),
        Index(
            "uq_project_grader_allocation_disease_encounter",
            "project_id", "user_id", "lab_unit_id", "encounter_set_type_id", "disease_id", "capacity",
            unique=True,
            postgresql_where=text("scope = 'disease_encounter'"),
        ),
        Index(
            "uq_project_grader_allocation_unified",
            "project_id", "user_id", "lab_unit_id", "encounter_set_type_id", "capacity",
            unique=True,
            postgresql_where=text("scope = 'encounter_set_unified'"),
        ),
        Index(
            "ix_project_grader_allocation_lookup",
            "project_id", "lab_unit_id", "scope", "capacity", "active",
        ),
    )
