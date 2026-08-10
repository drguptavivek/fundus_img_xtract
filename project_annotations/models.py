from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


LOCALIZATION_CHECK = "localization IN ('none','box','segmentation','box_or_segmentation')"
TOOL_CHECK = "tool_key IN ('box','rect','polygon','brush_mask','ellipse','pyramid')"


class ProjectAnnotationPolicy(Base):
    __tablename__ = "project_annotation_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    default_localization: Mapped[str] = mapped_column(String(32), nullable=False, default="box_or_segmentation", server_default="box_or_segmentation")
    preferred_tool_key: Mapped[str] = mapped_column(String(32), nullable=False, default="box", server_default="box")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    tools: Mapped[list["ProjectAnnotationTool"]] = relationship(back_populates="policy", cascade="all, delete-orphan", lazy="selectin")
    project_classes: Mapped[list["ProjectAnnotationClass"]] = relationship(back_populates="policy", cascade="all, delete-orphan", lazy="selectin")
    revisions: Mapped[list["ProjectAnnotationPolicyRevision"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan", lazy="raise"
    )

    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_project_annotation_policy_revision"),
        CheckConstraint(LOCALIZATION_CHECK.replace("localization", "default_localization"), name="ck_project_annotation_policy_localization"),
        CheckConstraint(TOOL_CHECK.replace("tool_key", "preferred_tool_key"), name="ck_project_annotation_policy_preferred_tool"),
    )


class ProjectAnnotationTool(Base):
    __tablename__ = "project_annotation_tools"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("project_annotation_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_key: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    settings_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    policy: Mapped[ProjectAnnotationPolicy] = relationship(back_populates="tools")

    __table_args__ = (
        UniqueConstraint("policy_id", "tool_key", name="uq_project_annotation_tool"),
        CheckConstraint(TOOL_CHECK, name="ck_project_annotation_tool_key"),
    )


class ProjectAnnotationClass(Base):
    __tablename__ = "project_annotation_classes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("project_annotation_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    localization: Mapped[str] = mapped_column(String(32), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    multiple_instances: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    policy: Mapped[ProjectAnnotationPolicy] = relationship(back_populates="project_classes")

    __table_args__ = (
        UniqueConstraint("policy_id", "key", name="uq_project_annotation_class_key"),
        CheckConstraint(LOCALIZATION_CHECK, name="ck_project_annotation_class_localization"),
        CheckConstraint("display_order >= 0", name="ck_project_annotation_class_display_order"),
        Index("ix_project_annotation_classes_policy_active", "policy_id", "active"),
        Index("ix_project_annotation_classes_policy_order", "policy_id", "display_order"),
    )


class ProjectAnnotationPolicyRevision(Base):
    __tablename__ = "project_annotation_policy_revisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("project_annotation_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    policy: Mapped[ProjectAnnotationPolicy] = relationship(back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("policy_id", "revision", name="uq_project_annotation_policy_revision"),
        CheckConstraint("revision >= 1", name="ck_project_annotation_policy_revision_number"),
    )
