"""ORM ownership for IITK API configuration and source identity."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


class IITKApiProjectConfig(Base):
    __tablename__ = "iitk_api_project_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_upload_profile_id: Mapped[int] = mapped_column(ForeignKey("project_upload_profiles.id", ondelete="RESTRICT"), nullable=False)
    encounter_set_type_id: Mapped[int] = mapped_column(ForeignKey("encounter_set_types.id", ondelete="RESTRICT"), nullable=False)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    secret_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    site_filter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_from_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project = relationship("Project")
    lab_unit = relationship("LabUnit")
    project_profile = relationship("ProjectUploadProfile")
    encounter_set_type = relationship("EncounterSetType")
    camera = relationship("Camera")
    sessions = relationship("IITKApiSessionLink", back_populates="config", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_iitk_api_project_config_project"),
        Index("ix_iitk_api_project_configs_active", "active"),
        Index("ix_iitk_api_project_configs_lab_unit_id", "lab_unit_id"),
    )


class IITKApiSessionLink(Base):
    __tablename__ = "iitk_api_session_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("iitk_api_project_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey("patient_encounters.id", ondelete="CASCADE"), nullable=False)
    source_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    local_image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inventory_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    config = relationship("IITKApiProjectConfig", back_populates="sessions")
    patient_encounter = relationship("PatientEncounters")

    __table_args__ = (
        CheckConstraint("source_status IN ('complete','partial')", name="ck_iitk_api_session_status"),
        UniqueConstraint("config_id", "source_session_id", name="uq_iitk_api_session_config_source"),
        UniqueConstraint("patient_encounter_id", name="uq_iitk_api_session_patient_encounter"),
        Index("ix_iitk_api_session_links_config_status", "config_id", "source_status"),
    )
