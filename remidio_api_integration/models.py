"""ORM models for Remidio API source routing.

These models are intentionally separate from Remidio ZIP upload defaults.
They route API-fetched Remidio source streams into project upload profiles.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


class RemidioApiSourceRule(Base):
    """A Remidio API source selector: connection + site custom identifier + device."""

    __tablename__ = "remidio_api_source_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remidio_connection_id: Mapped[int] = mapped_column(ForeignKey("remidio_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    remidio_site_id: Mapped[int | None] = mapped_column(ForeignKey("remidio_sites.id", ondelete="SET NULL"), nullable=True, index=True)
    site_custom_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    remidio_device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    connection: Mapped["RemidioConnection"] = relationship("RemidioConnection")
    site: Mapped["RemidioSite | None"] = relationship("RemidioSite")
    bindings: Mapped[List["ProjectUploadProfileRemidioApiBinding"]] = relationship(
        "ProjectUploadProfileRemidioApiBinding",
        back_populates="source_rule",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "uq_remidio_api_source_rule_active",
            "remidio_connection_id",
            "site_custom_identifier",
            "remidio_device_type",
            unique=True,
            postgresql_where=text("active IS TRUE"),
        ),
        Index(
            "ix_remidio_api_source_rule_lookup",
            "remidio_connection_id",
            "site_custom_identifier",
            "remidio_device_type",
            "active",
        ),
    )


class ProjectUploadProfileRemidioApiBinding(Base):
    """Workflow binding for one Remidio API source rule and project upload profile."""

    __tablename__ = "project_upload_profile_remidio_api_bindings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_upload_profile_id: Mapped[int] = mapped_column(
        ForeignKey("project_upload_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    remidio_api_source_rule_id: Mapped[int] = mapped_column(
        ForeignKey("remidio_api_source_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id", ondelete="RESTRICT"), nullable=False, index=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False, index=True)
    active_from_date: Mapped[date] = mapped_column(Date, nullable=False)
    active_to_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project_profile: Mapped["ProjectUploadProfile"] = relationship("ProjectUploadProfile", back_populates="remidio_api_bindings")
    source_rule: Mapped[RemidioApiSourceRule] = relationship("RemidioApiSourceRule", back_populates="bindings")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")
    camera: Mapped["Camera"] = relationship("Camera")

    __table_args__ = (
        CheckConstraint(
            "active_to_date IS NULL OR active_to_date >= active_from_date",
            name="ck_pup_remidio_api_binding_date_order",
        ),
        Index("ix_pup_remidio_api_binding_project_profile", "project_upload_profile_id"),
        Index("ix_pup_remidio_api_binding_source_rule", "remidio_api_source_rule_id"),
        Index("ix_pup_remidio_api_binding_active", "project_upload_profile_id", "active"),
        Index("ix_pup_remidio_api_binding_source_active", "remidio_api_source_rule_id", "active"),
    )


class RemidioApiExamEncounter(Base):
    """Association from one staged Remidio exam to one routed EncounterSet."""

    __tablename__ = "remidio_api_exam_encounters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remidio_exam_id: Mapped[int] = mapped_column(ForeignKey("remidio_exams.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey("patient_encounters.id", ondelete="CASCADE"), nullable=False, index=True)
    project_upload_profile_id: Mapped[int] = mapped_column(ForeignKey("project_upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    remidio_api_binding_id: Mapped[int] = mapped_column(
        ForeignKey("project_upload_profile_remidio_api_bindings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    remidio_exam: Mapped["RemidioExam"] = relationship("RemidioExam")
    patient_encounter: Mapped["PatientEncounters"] = relationship("PatientEncounters")
    project_profile: Mapped["ProjectUploadProfile"] = relationship("ProjectUploadProfile")
    binding: Mapped[ProjectUploadProfileRemidioApiBinding] = relationship("ProjectUploadProfileRemidioApiBinding")

    __table_args__ = (
        Index(
            "uq_remidio_api_exam_encounter_route",
            "remidio_exam_id",
            "project_upload_profile_id",
            "remidio_api_binding_id",
            unique=True,
        ),
        Index("uq_remidio_api_exam_encounter_patient", "patient_encounter_id", unique=True),
    )
