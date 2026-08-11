"""ORM persistence owned by the consolidated grading workbench."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class GradingWorkbenchSession(Base):
    __tablename__ = "grading_workbench_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    workflow: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active", index=True)
    root_task_id: Mapped[int | None] = mapped_column(ForeignKey("grading_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    encounter_set_package_id: Mapped[int | None] = mapped_column(ForeignKey("encounter_set_grading_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    queue_request_json: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False, default=dict)
    configuration_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_observations_json: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    draft_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_session_id: Mapped[int | None] = mapped_column(ForeignKey("grading_workbench_sessions.id", ondelete="SET NULL"), nullable=True)

    targets: Mapped[list["GradingWorkbenchSessionTarget"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin",
        foreign_keys="GradingWorkbenchSessionTarget.session_id",
    )

    __table_args__ = (
        CheckConstraint("role_slot IN ('resident','resident2','arbitrator','review','regrade_adj')", name="ck_gws_role_slot"),
        CheckConstraint("status IN ('active','completed','released','expired','invalidated')", name="ck_gws_status"),
        CheckConstraint("token_generation >= 1", name="ck_gws_token_generation"),
        Index(
            "uq_gws_active_user_slot",
            "user_id",
            "role_slot",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_gws_active_expiry", "status", "idle_expires_at", "absolute_expires_at"),
    )


class GradingWorkbenchSessionTarget(Base):
    __tablename__ = "grading_workbench_session_targets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("grading_workbench_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("grading_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    target_purpose: Mapped[str] = mapped_column(String(24), nullable=False, default="editable", server_default="editable")
    acquired_task_state: Mapped[str] = mapped_column(String(24), nullable=False)
    acquired_grade_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    release_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    session: Mapped[GradingWorkbenchSession] = relationship(back_populates="targets", foreign_keys=[session_id])

    __table_args__ = (
        UniqueConstraint("session_id", "task_id", "role_slot", name="uq_gwst_session_task_slot"),
        CheckConstraint("target_purpose IN ('editable','evidence','followup')", name="ck_gwst_purpose"),
        Index(
            "uq_gwst_active_task_slot",
            "task_id",
            "role_slot",
            unique=True,
            postgresql_where=text("released_at IS NULL AND target_purpose = 'editable'"),
            sqlite_where=text("released_at IS NULL AND target_purpose = 'editable'"),
        ),
    )


class GradingSubmissionEvent(Base):
    __tablename__ = "grading_submission_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    workflow: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    result_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("grading_workbench_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    root_task_id: Mapped[int | None] = mapped_column(ForeignKey("grading_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    encounter_set_package_id: Mapped[int | None] = mapped_column(ForeignKey("encounter_set_grading_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    lab_unit_id: Mapped[int | None] = mapped_column(ForeignKey("lab_units.id", ondelete="SET NULL"), nullable=True, index=True)
    source_profile_id: Mapped[int | None] = mapped_column(ForeignKey("upload_profiles.id", ondelete="SET NULL"), nullable=True)
    source_lineage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    configuration_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_revisions_json: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    diagnostic_metadata_json: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    specialized_record_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    specialized_record_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)

    items: Mapped[list["GradingSubmissionEventItem"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )
    session: Mapped[GradingWorkbenchSession | None] = relationship(
        foreign_keys=[session_id], lazy="joined"
    )

    __table_args__ = (
        CheckConstraint("outcome IN ('accepted','rejected','conflict')", name="ck_gse_outcome"),
        UniqueConstraint("session_id", "idempotency_key", name="uq_gse_session_idempotency"),
        Index("ix_gse_actor_created", "actor_user_id", "created_at"),
    )


class GradingSubmissionEventItem(Base):
    __tablename__ = "grading_submission_event_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("grading_submission_events.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("grading_tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    grade_id: Mapped[int | None] = mapped_column(ForeignKey("grades.id", ondelete="SET NULL"), nullable=True, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False)
    target_level: Mapped[str] = mapped_column(String(24), nullable=False)
    grade_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    before_json: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    after_json: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    annotation_set_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    event: Mapped[GradingSubmissionEvent] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("event_id", "task_id", name="uq_gsei_event_task"),
        CheckConstraint("target_level IN ('image','encounter')", name="ck_gsei_target_level"),
        CheckConstraint("grade_revision >= 1", name="ck_gsei_grade_revision"),
    )


class AnnotationSet(Base):
    __tablename__ = "annotation_sets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    grade_id: Mapped[int | None] = mapped_column(ForeignKey("grades.id", ondelete="CASCADE"), nullable=True, unique=True)
    intra_rater_grade_id: Mapped[int | None] = mapped_column(ForeignKey("intra_rater_grades.id", ondelete="CASCADE"), nullable=True, unique=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    policy_source: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    instances: Mapped[list["AnnotationInstance"]] = relationship(
        back_populates="annotation_set", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "(grade_id IS NOT NULL AND intra_rater_grade_id IS NULL) OR "
            "(grade_id IS NULL AND intra_rater_grade_id IS NOT NULL)",
            name="ck_annotation_set_single_owner",
        ),
        CheckConstraint("schema_version >= 1", name="ck_annotation_set_schema_version"),
        CheckConstraint("policy_revision >= 0", name="ck_annotation_set_policy_revision"),
    )


class AnnotationInstance(Base):
    __tablename__ = "annotation_instances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid4()))
    annotation_set_id: Mapped[int] = mapped_column(ForeignKey("annotation_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    image_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    class_source: Mapped[str] = mapped_column(String(32), nullable=False)
    grading_feature_id: Mapped[int | None] = mapped_column(ForeignKey("gradings_features.id", ondelete="SET NULL"), nullable=True, index=True)
    project_class_id: Mapped[int | None] = mapped_column(ForeignKey("project_annotation_classes.id", ondelete="SET NULL"), nullable=True, index=True)
    class_key_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    class_label_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    geometry_json: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    bbox_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    instance_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    annotation_set: Mapped[AnnotationSet] = relationship(back_populates="instances")
    mask_tiles: Mapped[list["AnnotationMaskTile"]] = relationship(
        back_populates="annotation_instance", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("class_source IN ('grading_feature','project_class')", name="ck_annotation_instance_class_source"),
        CheckConstraint(
            "(class_source = 'grading_feature' AND grading_feature_id IS NOT NULL AND project_class_id IS NULL) OR "
            "(class_source = 'project_class' AND grading_feature_id IS NULL AND project_class_id IS NOT NULL)",
            name="ck_annotation_instance_class_identity",
        ),
        CheckConstraint("geometry_type IN ('none','box','rect','polygon','brush_mask','ellipse','pyramid')", name="ck_annotation_instance_geometry_type"),
        CheckConstraint("policy_revision >= 0", name="ck_annotation_instance_policy_revision"),
        CheckConstraint("instance_order >= 0", name="ck_annotation_instance_order"),
        Index("ix_annotation_instance_set_order", "annotation_set_id", "instance_order"),
    )


class AnnotationMaskTile(Base):
    __tablename__ = "annotation_mask_tiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    annotation_instance_id: Mapped[int] = mapped_column(ForeignKey("annotation_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    tile_x: Mapped[int] = mapped_column(Integer, nullable=False)
    tile_y: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    png_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    annotation_instance: Mapped[AnnotationInstance] = relationship(back_populates="mask_tiles")

    __table_args__ = (
        UniqueConstraint("annotation_instance_id", "tile_x", "tile_y", name="uq_annotation_mask_tile_position"),
        CheckConstraint("tile_x >= 0 AND tile_y >= 0", name="ck_annotation_mask_tile_coordinates"),
        CheckConstraint("width BETWEEN 1 AND 256 AND height BETWEEN 1 AND 256", name="ck_annotation_mask_tile_dimensions"),
    )
