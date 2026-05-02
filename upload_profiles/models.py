"""Upload profile ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


class UploadProfile(Base):
    """Reusable upload workflow profile assignable to many uploaders."""

    __tablename__ = "upload_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    allow_mydriatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    allow_non_mydriatic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    default_is_mydriatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")
    project: Mapped["Project"] = relationship("Project", back_populates="upload_profiles")
    assignments: Mapped[List["UploadProfileAssignment"]] = relationship(
        "UploadProfileAssignment",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    diseases: Mapped[List["UploadProfileDisease"]] = relationship(
        "UploadProfileDisease",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    cameras: Mapped[List["UploadProfileCamera"]] = relationship(
        "UploadProfileCamera",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    areas: Mapped[List["UploadProfileArea"]] = relationship(
        "UploadProfileArea",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    upload_kinds: Mapped[List["UploadProfileKind"]] = relationship(
        "UploadProfileKind",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    ai_workflows: Mapped[List["UploadProfileAIWorkflow"]] = relationship(
        "UploadProfileAIWorkflow",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("lab_unit_id", "project_id", "name", name="uq_upload_profile_lab_project_name"),
        CheckConstraint(
            "(allow_mydriatic = true) OR (allow_non_mydriatic = true)",
            name="ck_upload_profile_allows_any_mydriatic_state",
        ),
        CheckConstraint(
            "(default_is_mydriatic = false) OR (allow_mydriatic = true)",
            name="ck_upload_profile_default_mydriatic_allowed",
        ),
        CheckConstraint(
            "(default_is_mydriatic = true) OR (allow_non_mydriatic = true)",
            name="ck_upload_profile_default_nonmydriatic_allowed",
        ),
        Index("ix_upload_profiles_lab_project_active", "lab_unit_id", "project_id", "active"),
    )


class UploadProfileAssignment(Base):
    """Uploader assignment for a reusable upload profile."""

    __tablename__ = "upload_profile_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="assignments")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("upload_profile_id", "user_id", name="uq_upload_profile_assignment_user"),
        Index("ix_upload_profile_assignments_user_active", "user_id", "active"),
    )


class UploadProfileDisease(Base):
    """Allowed and optional default disease target for an upload profile."""

    __tablename__ = "upload_profile_diseases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="CASCADE"), nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, server_default="false")

    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="diseases")
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("upload_profile_id", "disease_id", name="uq_upload_profile_disease"),
        Index("ix_upload_profile_diseases_profile_default", "upload_profile_id", "is_default"),
    )


class UploadProfileCamera(Base):
    """Allowed camera entry for an upload profile."""

    __tablename__ = "upload_profile_cameras"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)

    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="cameras")
    camera: Mapped["Camera"] = relationship("Camera")

    __table_args__ = (
        UniqueConstraint("upload_profile_id", "camera_id", name="uq_upload_profile_camera"),
    )


class UploadProfileArea(Base):
    """Allowed site/area entry for an upload profile."""

    __tablename__ = "upload_profile_areas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id", ondelete="CASCADE"), nullable=False, index=True)

    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="areas")
    area: Mapped["Area"] = relationship("Area")

    __table_args__ = (
        UniqueConstraint("upload_profile_id", "area_id", name="uq_upload_profile_area"),
    )


class UploadProfileKind(Base):
    """Allowed upload kind for a profile."""

    __tablename__ = "upload_profile_kinds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    upload_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="upload_kinds")

    __table_args__ = (
        UniqueConstraint("upload_profile_id", "upload_kind", name="uq_upload_profile_kind"),
        CheckConstraint(
            "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')",
            name="ck_upload_profile_kind_valid",
        ),
    )


class UploadProfileAIWorkflow(Base):
    """AI workflow allowed by a profile for one disease and upload kind."""

    __tablename__ = "upload_profile_ai_workflows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="CASCADE"), nullable=False, index=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False, index=True)
    upload_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")

    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="ai_workflows")
    disease: Mapped["Disease"] = relationship("Disease")
    ai_model: Mapped["AIModel"] = relationship("AIModel")

    __table_args__ = (
        UniqueConstraint("upload_profile_id", "disease_id", "ai_model_id", "upload_kind", name="uq_upload_profile_ai_workflow"),
        CheckConstraint(
            "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')",
            name="ck_upload_profile_ai_workflow_kind_valid",
        ),
    )


class PatientEncounterTargetDisease(Base):
    """Disease target selected for an encounter-set upload profile."""

    __tablename__ = "patient_encounter_target_diseases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey("patient_encounters.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="CASCADE"), nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    patient_encounter: Mapped["PatientEncounters"] = relationship("PatientEncounters")
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("patient_encounter_id", "disease_id", name="uq_patient_encounter_target_disease"),
        Index("ix_patient_encounter_target_disease_default", "patient_encounter_id", "is_default"),
    )
