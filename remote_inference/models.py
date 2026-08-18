"""ORM models for project-scoped remote inference policies."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


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


class ProjectAutomatedRemoteInferenceRule(Base):
    """Project-owned automated inference rule for one supported upload path."""

    __tablename__ = "project_automated_remote_inference_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False, index=True)
    upload_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_timing: Mapped[str] = mapped_column(String(32), nullable=False, default="on_image_received", server_default="on_image_received")
    encounter_eligibility: Mapped[str] = mapped_column(String(64), nullable=False, default="always", server_default="always")
    image_selection: Mapped[str] = mapped_column(String(64), nullable=False, default="all_eligible_images", server_default="all_eligible_images")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project")
    disease: Mapped["Disease"] = relationship("Disease")
    ai_model: Mapped["AIModel"] = relationship("AIModel")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "disease_id", "ai_model_id", "upload_kind",
            name="uq_project_automated_remote_inference_rule",
        ),
        CheckConstraint(
            "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')",
            name="ck_project_automated_remote_inference_upload_kind",
        ),
        CheckConstraint(
            "trigger_timing IN ('on_image_received','on_report_received','after_verification')",
            name="ck_project_automated_remote_inference_trigger",
        ),
        CheckConstraint(
            "encounter_eligibility IN ('always','if_matching_report_present','if_matching_report_absent','if_any_report_present')",
            name="ck_project_automated_remote_inference_eligibility",
        ),
        CheckConstraint(
            "image_selection IN ('all_eligible_images','disc_focused_images','macula_focused_images','disc_or_macula_images')",
            name="ck_project_automated_remote_inference_image_selection",
        ),
        Index("ix_project_automated_remote_inference_project_active", "project_id", "active"),
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


class ProjectEncounterAIWorkflow(Base):
    """Project-owned controls for one encounter-scoped model workflow."""

    __tablename__ = "project_encounter_ai_workflows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False, index=True)
    workflow_key: Mapped[str] = mapped_column(String(64), nullable=False, default="dr_dme", server_default="dr_dme")
    automatic_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    manual_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    automatic_eligibility: Mapped[str] = mapped_column(String(64), nullable=False, default="always", server_default="always")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project")
    ai_model: Mapped["AIModel"] = relationship("AIModel")

    __table_args__ = (
        UniqueConstraint("project_id", "workflow_key", name="uq_project_encounter_ai_workflow"),
        CheckConstraint("workflow_key IN ('dr_dme')", name="ck_project_encounter_ai_workflow_key"),
        CheckConstraint(
            "automatic_eligibility IN ('always','if_dr_ocr_report_present')",
            name="ck_project_encounter_ai_workflow_eligibility",
        ),
        Index("ix_project_encounter_ai_workflow_project_active", "project_id", "active"),
    )


class EncounterAIOutputTarget(Base):
    """Provider-label mapping for one output disease of an encounter model."""

    __tablename__ = "encounter_ai_output_targets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False, index=True)
    target_key: Mapped[str] = mapped_column(String(64), nullable=False)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    label_mapping_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    ai_model: Mapped["AIModel"] = relationship("AIModel")
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("ai_model_id", "target_key", name="uq_encounter_ai_output_target"),
        UniqueConstraint("ai_model_id", "disease_id", name="uq_encounter_ai_output_target_disease"),
    )


class EncounterAIInferenceRun(Base):
    """Durable, idempotent encounter-level screening request and response."""

    __tablename__ = "encounter_ai_inference_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, default=lambda: str(uuid4()))
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey("patient_encounters.id", ondelete="CASCADE"), nullable=False, index=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False, index=True)
    integration_id: Mapped[int | None] = mapped_column(ForeignKey("ai_model_integrations.id", ondelete="SET NULL"), nullable=True, index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="automatic", server_default="automatic")
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    report_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", server_default="queued", index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_manifest_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    presign_response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submit_response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    config_snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    patient_encounter: Mapped["PatientEncounters"] = relationship("PatientEncounters")
    ai_model: Mapped["AIModel"] = relationship("AIModel")
    integration: Mapped["AIModelIntegration | None"] = relationship("AIModelIntegration")
    requested_by: Mapped["User | None"] = relationship("User")
    image_results: Mapped[list["EncounterAIImageResult"]] = relationship(
        "EncounterAIImageResult", back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("patient_encounter_id", "ai_model_id", name="uq_encounter_ai_run_encounter_model"),
        CheckConstraint("source IN ('automatic','manual','recovery')", name="ck_encounter_ai_run_source"),
        CheckConstraint(
            "status IN ('queued','presigning','uploading','submitting','success','partial','failed')",
            name="ck_encounter_ai_run_status",
        ),
        Index("ix_encounter_ai_run_encounter_created", "patient_encounter_id", "created_at"),
    )


class EncounterAIImageResult(Base):
    """Per-image remote evidence and local lineage for an encounter run."""

    __tablename__ = "encounter_ai_image_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("encounter_ai_inference_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_set_image_id: Mapped[int] = mapped_column(ForeignKey("encounter_set_images.id", ondelete="RESTRICT"), nullable=False, index=True)
    remote_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    submitted_eye: Mapped[str] = mapped_column(String(8), nullable=False)
    detected_eye: Mapped[str | None] = mapped_column(String(16), nullable=True)
    laterality_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    upload_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    quality_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    raw_output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    run: Mapped["EncounterAIInferenceRun"] = relationship("EncounterAIInferenceRun", back_populates="image_results")
    encounter_set_image: Mapped["EncounterSetImage"] = relationship("EncounterSetImage")
    target_results: Mapped[list["EncounterAITargetResult"]] = relationship(
        "EncounterAITargetResult", back_populates="image_result", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("run_id", "encounter_set_image_id", name="uq_encounter_ai_image_result"),
        CheckConstraint("submitted_eye IN ('left','right')", name="ck_encounter_ai_image_submitted_eye"),
        CheckConstraint(
            "quality_state IN ('pending','gradable','ungradable','error')",
            name="ck_encounter_ai_image_quality_state",
        ),
    )


class EncounterAITargetResult(Base):
    """Mapped disease result and resulting AI grade for one returned image."""

    __tablename__ = "encounter_ai_target_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_result_id: Mapped[int] = mapped_column(ForeignKey("encounter_ai_image_results.id", ondelete="CASCADE"), nullable=False, index=True)
    output_target_id: Mapped[int] = mapped_column(ForeignKey("encounter_ai_output_targets.id", ondelete="RESTRICT"), nullable=False, index=True)
    raw_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    mapped_grade: Mapped[str] = mapped_column(String(128), nullable=False)
    derivation_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    grade_id: Mapped[int | None] = mapped_column(ForeignKey("grades.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    image_result: Mapped["EncounterAIImageResult"] = relationship("EncounterAIImageResult", back_populates="target_results")
    output_target: Mapped["EncounterAIOutputTarget"] = relationship("EncounterAIOutputTarget")
    grade: Mapped["Grade | None"] = relationship("Grade")

    __table_args__ = (
        UniqueConstraint("image_result_id", "output_target_id", name="uq_encounter_ai_target_result"),
        CheckConstraint(
            "derivation_reason IN ('provider','similarity_threshold','provider_error')",
            name="ck_encounter_ai_target_derivation",
        ),
    )
