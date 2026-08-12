"""ORM models for project-scoped application role grants."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from models import Hospital, LabUnit, Project, Role, User


PROJECT_SCOPE = "project"
HOSPITAL_SCOPE = "hospital"
LAB_UNIT_SCOPE = "lab_unit"
PROJECT_SCOPE_TYPES = frozenset({PROJECT_SCOPE, HOSPITAL_SCOPE, LAB_UNIT_SCOPE})


class ProjectRoleGrant(Base):
    """Assign one globally defined application role inside one project scope."""

    __tablename__ = "project_role_grants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    hospital_id: Mapped[int | None] = mapped_column(
        ForeignKey("hospitals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    lab_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("lab_units.id", ondelete="CASCADE"), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship("Project")
    user: Mapped["User"] = relationship("User")
    role: Mapped["Role"] = relationship("Role")
    hospital: Mapped["Hospital | None"] = relationship("Hospital")
    lab_unit: Mapped["LabUnit | None"] = relationship("LabUnit")

    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('project','hospital','lab_unit')",
            name="ck_project_role_grants_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'project' AND hospital_id IS NULL AND lab_unit_id IS NULL) OR "
            "(scope_type = 'hospital' AND hospital_id IS NOT NULL AND lab_unit_id IS NULL) OR "
            "(scope_type = 'lab_unit' AND hospital_id IS NULL AND lab_unit_id IS NOT NULL)",
            name="ck_project_role_grants_scope_target",
        ),
        Index(
            "uq_project_role_grants_project_scope",
            "project_id", "user_id", "role_id",
            unique=True,
            postgresql_where=text("scope_type = 'project'"),
            sqlite_where=text("scope_type = 'project'"),
        ),
        Index(
            "uq_project_role_grants_hospital_scope",
            "project_id", "user_id", "role_id", "hospital_id",
            unique=True,
            postgresql_where=text("scope_type = 'hospital'"),
            sqlite_where=text("scope_type = 'hospital'"),
        ),
        Index(
            "uq_project_role_grants_lab_scope",
            "project_id", "user_id", "role_id", "lab_unit_id",
            unique=True,
            postgresql_where=text("scope_type = 'lab_unit'"),
            sqlite_where=text("scope_type = 'lab_unit'"),
        ),
        Index(
            "ix_project_role_grants_lookup",
            "user_id", "project_id", "role_id", "active",
        ),
    )
