"""ORM models for project-scoped remote inference policies."""
from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


class RemoteInferencePolicy(Base):
    """Reusable remote inference policy assigned to one or more projects."""

    __tablename__ = "remote_inference_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    rules: Mapped[List["RemoteInferencePolicyRule"]] = relationship(
        "RemoteInferencePolicyRule",
        back_populates="policy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    project_assignments: Mapped[List["ProjectRemoteInferencePolicy"]] = relationship(
        "ProjectRemoteInferencePolicy",
        back_populates="policy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RemoteInferencePolicyRule(Base):
    """Disease/model-specific rule inside a remote inference policy."""

    __tablename__ = "remote_inference_policy_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("remote_inference_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False, index=True)
    upload_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_timing: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    encounter_eligibility: Mapped[str] = mapped_column(String(64), nullable=False, default="always", server_default="always")
    image_selection: Mapped[str] = mapped_column(String(64), nullable=False, default="all_eligible_images", server_default="all_eligible_images")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    policy: Mapped["RemoteInferencePolicy"] = relationship("RemoteInferencePolicy", back_populates="rules")
    disease: Mapped["Disease"] = relationship("Disease")
    ai_model: Mapped["AIModel"] = relationship("AIModel")

    __table_args__ = (
        UniqueConstraint("policy_id", "disease_id", "ai_model_id", "upload_kind", name="uq_remote_inference_policy_rule"),
        CheckConstraint(
            "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')",
            name="ck_remote_inference_rule_upload_kind",
        ),
        CheckConstraint(
            "trigger_timing IN ('on_image_received','on_report_received','after_verification','manual_only')",
            name="ck_remote_inference_rule_trigger",
        ),
        CheckConstraint(
            "encounter_eligibility IN ('always','if_matching_report_present','if_matching_report_absent','if_any_report_present')",
            name="ck_remote_inference_rule_encounter_eligibility",
        ),
        CheckConstraint(
            "image_selection IN ('all_eligible_images','disc_focused_images','macula_focused_images','disc_or_macula_images')",
            name="ck_remote_inference_rule_image_selection",
        ),
        Index("ix_remote_inference_rules_policy_active", "policy_id", "active"),
    )


class DiseaseReportLinkage(Base):
    """Explicit mapping between a disease and a normalized report source/type."""

    __tablename__ = "disease_report_linkages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="CASCADE"), nullable=False, index=True)
    report_source: Mapped[str] = mapped_column(String(64), nullable=False, default="remidio", server_default="remidio")
    report_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("disease_id", "report_source", "report_type", name="uq_disease_report_linkage"),
        CheckConstraint("report_source IN ('remidio')", name="ck_disease_report_linkage_source"),
        CheckConstraint("report_type IN ('dr','amd','glaucoma')", name="ck_disease_report_linkage_type"),
        Index("ix_disease_report_linkages_disease_active", "disease_id", "active"),
    )


class ProjectRemoteInferencePolicy(Base):
    """Project-level assignment of one remote inference policy."""

    __tablename__ = "project_remote_inference_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    remote_inference_policy_id: Mapped[int] = mapped_column(
        ForeignKey("remote_inference_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project")
    policy: Mapped["RemoteInferencePolicy"] = relationship("RemoteInferencePolicy", back_populates="project_assignments")

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_remote_inference_policy_project"),
        Index("ix_project_remote_inference_policies_project_active", "project_id", "active"),
    )


class ProjectManualRemoteInferenceWorkflow(Base):
    """Project-owned permission to submit images to a remote model manually."""

    __tablename__ = "project_manual_remote_inference_workflows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False, index=True)
    upload_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project")
    disease: Mapped["Disease"] = relationship("Disease")
    ai_model: Mapped["AIModel"] = relationship("AIModel")

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "disease_id",
            "ai_model_id",
            "upload_kind",
            name="uq_project_manual_remote_inference_workflow",
        ),
        CheckConstraint(
            "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')",
            name="ck_project_manual_remote_inference_upload_kind",
        ),
        Index(
            "ix_project_manual_remote_inference_project_active",
            "project_id",
            "active",
        ),
    )
