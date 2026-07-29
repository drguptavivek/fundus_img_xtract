"""Upload profile ORM models."""
from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.utils import utcnow
from models import Base


class UploadProfile(Base):
    """Reusable upload workflow template mapped to projects and uploaders."""

    __tablename__ = "upload_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    allow_mydriatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    allow_non_mydriatic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    default_is_mydriatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    automated_remidio_populated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    allow_remidio_zip_encounter_set: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    allow_iitk_zip_encounter_set: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    task_prioritization_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project_mappings: Mapped[List["ProjectUploadProfile"]] = relationship(
        "ProjectUploadProfile",
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
    encounter_set_types: Mapped[List["UploadProfileEncounterSetType"]] = relationship(
        "UploadProfileEncounterSetType",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
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
        Index("ix_upload_profiles_active_name", "active", "name"),
    )


class ProjectUploadProfile(Base):
    """Project-level enablement for a reusable upload profile template."""

    __tablename__ = "project_upload_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="upload_profile_mappings")
    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="project_mappings")
    assignments: Mapped[List["ProjectUploadProfileAssignment"]] = relationship(
        "ProjectUploadProfileAssignment",
        back_populates="project_profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    remidio_api_bindings: Mapped[List["ProjectUploadProfileRemidioApiBinding"]] = relationship(
        "ProjectUploadProfileRemidioApiBinding",
        back_populates="project_profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "upload_profile_id", name="uq_project_upload_profile"),
        Index("ix_project_upload_profiles_project_active", "project_id", "active"),
        Index("ix_project_upload_profiles_profile_active", "upload_profile_id", "active"),
    )


class ProjectUploadProfileAssignment(Base):
    """Uploader and lab-unit assignment for one project-profile enablement."""

    __tablename__ = "project_upload_profile_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_upload_profile_id: Mapped[int] = mapped_column(
        ForeignKey("project_upload_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id", ondelete="CASCADE"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project_profile: Mapped["ProjectUploadProfile"] = relationship("ProjectUploadProfile", back_populates="assignments")
    user: Mapped["User"] = relationship("User")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")

    __table_args__ = (
        UniqueConstraint("project_upload_profile_id", "user_id", "lab_unit_id", name="uq_project_upload_profile_assignment"),
        Index("ix_project_upload_profile_assignments_user_active", "user_id", "active"),
        Index("ix_project_upload_profile_assignments_lab_active", "lab_unit_id", "active"),
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
    auto_inference_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="always", server_default="always")
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
        CheckConstraint(
            "auto_inference_policy IN ('never','always','remidio_glaucoma_report_present')",
            name="ck_upload_profile_ai_workflow_auto_policy",
        ),
    )


class UploadProfileEncounterSetType(Base):
    """EncounterSetType workflow configuration for encounter-set upload profiles."""

    __tablename__ = "upload_profile_encounter_set_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_id: Mapped[int] = mapped_column(ForeignKey("upload_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_set_type_id: Mapped[int] = mapped_column(ForeignKey("encounter_set_types.id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_grading_scheme_id: Mapped[int | None] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=True, index=True)
    default_image_grading_scheme_id: Mapped[int | None] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    profile: Mapped["UploadProfile"] = relationship("UploadProfile", back_populates="encounter_set_types")
    encounter_set_type: Mapped["EncounterSetType"] = relationship("EncounterSetType")
    encounter_grading_scheme: Mapped["Disease | None"] = relationship("Disease", foreign_keys=[encounter_grading_scheme_id])
    default_image_grading_scheme: Mapped["Disease | None"] = relationship("Disease", foreign_keys=[default_image_grading_scheme_id])
    image_grading_schemes: Mapped[List["UploadProfileEncounterSetTypeImageGradingScheme"]] = relationship(
        "UploadProfileEncounterSetTypeImageGradingScheme",
        back_populates="profile_encounter_set_type",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UploadProfileEncounterSetTypeImageGradingScheme.display_order",
    )
    grading_packages: Mapped[List["UploadProfileEncounterSetTypeGradingPackage"]] = relationship(
        "UploadProfileEncounterSetTypeGradingPackage",
        back_populates="profile_encounter_set_type",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UploadProfileEncounterSetTypeGradingPackage.display_order",
    )

    __table_args__ = (
        UniqueConstraint("upload_profile_id", "encounter_set_type_id", name="uq_upload_profile_encounter_set_type"),
        Index("ix_upload_profile_est_profile_active", "upload_profile_id", "active"),
    )


class UploadProfileEncounterSetTypeImageGradingScheme(Base):
    """Image-level grading scheme allow-list for one upload-profile EncounterSetType mapping."""

    __tablename__ = "upload_profile_est_image_grading_schemes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_encounter_set_type_id: Mapped[int] = mapped_column(
        ForeignKey("upload_profile_encounter_set_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, server_default="false")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    profile_encounter_set_type: Mapped["UploadProfileEncounterSetType"] = relationship(
        "UploadProfileEncounterSetType",
        back_populates="image_grading_schemes",
    )
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("upload_profile_encounter_set_type_id", "disease_id", name="uq_up_est_image_grading_scheme"),
        Index("ix_up_est_img_scheme_mapping_active", "upload_profile_encounter_set_type_id", "active"),
        Index("ix_up_est_img_scheme_default", "upload_profile_encounter_set_type_id", "is_default"),
    )


class UploadProfileEncounterSetTypeGradingPackage(Base):
    """Configured grading package for one profile EncounterSetType mapping."""

    __tablename__ = "upload_profile_est_grading_packages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_profile_encounter_set_type_id: Mapped[int] = mapped_column(
        ForeignKey("upload_profile_encounter_set_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    applicability: Mapped[str] = mapped_column(String(64), nullable=False, default="always", server_default="always")
    default_image_grading_scheme_id: Mapped[int | None] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=True, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    profile_encounter_set_type: Mapped["UploadProfileEncounterSetType"] = relationship(
        "UploadProfileEncounterSetType",
        back_populates="grading_packages",
    )
    default_image_grading_scheme: Mapped["Disease | None"] = relationship("Disease", foreign_keys=[default_image_grading_scheme_id])
    image_grading_schemes: Mapped[List["UploadProfileEncounterSetTypePackageImageScheme"]] = relationship(
        "UploadProfileEncounterSetTypePackageImageScheme",
        back_populates="package",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UploadProfileEncounterSetTypePackageImageScheme.display_order",
    )
    encounter_grading_schemes: Mapped[List["UploadProfileEncounterSetTypePackageEncounterScheme"]] = relationship(
        "UploadProfileEncounterSetTypePackageEncounterScheme",
        back_populates="package",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UploadProfileEncounterSetTypePackageEncounterScheme.display_order",
    )

    __table_args__ = (
        UniqueConstraint("upload_profile_encounter_set_type_id", "code", name="uq_up_est_grading_package_code"),
        CheckConstraint(
            "applicability IN ('always','remidio_dr_report_present','remidio_amd_report_present','remidio_glaucoma_report_present','manual_only','disabled')",
            name="ck_up_est_grading_package_applicability",
        ),
        Index("ix_up_est_grading_package_mapping_active", "upload_profile_encounter_set_type_id", "active"),
    )


class UploadProfileEncounterSetTypePackageImageScheme(Base):
    """Image-level scheme included in one configured EncounterSet grading package."""

    __tablename__ = "upload_profile_est_package_image_schemes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("upload_profile_est_grading_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, server_default="false")
    auto_create_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="always", server_default="always")
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    package: Mapped["UploadProfileEncounterSetTypeGradingPackage"] = relationship(
        "UploadProfileEncounterSetTypeGradingPackage",
        back_populates="image_grading_schemes",
    )
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("package_id", "disease_id", name="uq_up_est_pkg_image_scheme"),
        CheckConstraint(
            "auto_create_policy IN ('never','always','remidio_dr_report_present','remidio_amd_report_present','remidio_glaucoma_report_present')",
            name="ck_up_est_pkg_image_auto_create_policy",
        ),
        Index("ix_up_est_pkg_image_scheme_package_active", "package_id", "active"),
    )


class UploadProfileEncounterSetTypePackageEncounterScheme(Base):
    """Encounter-level scheme included in one configured EncounterSet grading package."""

    __tablename__ = "upload_profile_est_package_encounter_schemes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("upload_profile_est_grading_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    package: Mapped["UploadProfileEncounterSetTypeGradingPackage"] = relationship(
        "UploadProfileEncounterSetTypeGradingPackage",
        back_populates="encounter_grading_schemes",
    )
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("package_id", "disease_id", name="uq_up_est_pkg_encounter_scheme"),
        Index("ix_up_est_pkg_encounter_scheme_package_active", "package_id", "active"),
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
