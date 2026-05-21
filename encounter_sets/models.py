"""Encounter-set supporting asset ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base

if TYPE_CHECKING:
    from models import Hospital, PatientEncounters, Project, S3Config, UploadProfile, User


class EncounterSetAttachment(Base):
    """Supporting encounter-set attachment that never creates grading tasks."""

    __tablename__ = "encounter_set_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid4()), nullable=False)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey("patient_encounters.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    folder_rel: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_pii: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    visible_to_grader: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    creates_task: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    upload_profile_id: Mapped[int | None] = mapped_column(ForeignKey("upload_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id", ondelete="SET NULL"), nullable=True, index=True)
    s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True, index=True)
    s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    patient_encounter: Mapped["PatientEncounters"] = relationship("PatientEncounters", back_populates="encounter_set_attachments")
    project: Mapped["Project | None"] = relationship("Project")
    upload_profile: Mapped["UploadProfile | None"] = relationship("UploadProfile")
    hospital: Mapped["Hospital | None"] = relationship("Hospital")
    s3_config: Mapped["S3Config | None"] = relationship("S3Config")
    created_by: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        CheckConstraint("asset_kind IN ('document','pdf','document_image')", name="ck_encounter_set_attachment_asset_kind"),
        CheckConstraint("creates_task = false", name="ck_encounter_set_attachment_never_creates_task"),
        CheckConstraint("stored_filename IS NULL OR position('/' in stored_filename) = 0", name="ck_encounter_set_attachment_stored_filename_no_slash"),
        Index("ix_esa_encounter_kind", "patient_encounter_id", "asset_kind"),
        Index("ix_esa_project_kind", "project_id", "asset_kind"),
        Index("ix_esa_s3_config_uuid", "s3_config_id", "uuid"),
    )
