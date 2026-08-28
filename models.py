import logging
import os
from pathlib import Path
from urllib.parse import quote, urlparse
from sqlalchemy import (CheckConstraint, Date, create_engine, Integer, BigInteger, String, ForeignKey, Boolean, DateTime, Text, Index, UniqueConstraint, Table, Column, Float, event, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, relationship, Mapped, mapped_column
from datetime import date, datetime, timezone
from typing import Optional, List
from uuid import uuid4

from utils.env_loader import load_environment
from auth.utils import utcnow
from utils.log_sanitize import sanitize_log_value
from db_base import Base

load_environment()

BASE_DIR = Path(__file__).resolve().parent
_LOGGER = logging.getLogger(__name__)


def _build_database_url(base_dir: Path) -> str:
    """Construct a database URL from available environment variables."""

    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        parsed = urlparse(explicit_url)
        if parsed.scheme.startswith("postgres") and parsed.username and parsed.password is None:
            raise ValueError("DATABASE_URL must include a password for PostgreSQL connections.")
        return explicit_url

    postgres_db = (os.getenv("POSTGRES_APP_DB") or "").strip()
    postgres_user = (os.getenv("POSTGRES_APP_USER") or "").strip()
    host_override = os.getenv("POSTGRES_HOST_OVERRIDE") or os.getenv("POSTGRES_HOST_LOCAL")
    postgres_host_raw = host_override if host_override and host_override.strip() else os.getenv("POSTGRES_HOST")
    postgres_host = (postgres_host_raw or "127.0.0.1").strip()
    postgres_password = os.getenv("POSTGRES_APP_PASSWORD")
    raw_port = os.getenv("POSTGRES_PORT")
    postgres_port = raw_port.strip() if raw_port else "5432"

    if postgres_db and postgres_user:
        user_part = quote(postgres_user, safe="")
        password_part = ""
        if postgres_password and postgres_password.strip():
            password_part = f":{quote(postgres_password.strip(), safe='')}"
        else:
            raise ValueError("POSTGRES_APP_PASSWORD must be set for PostgreSQL connections.")

        host_part = postgres_host or "127.0.0.1"
        port_part = f":{postgres_port}" if postgres_port else ""
        # print(f"postgresql://{user_part}{password_part}@{host_part}{port_part}/{postgres_db} ")
        return f"postgresql://{user_part}{password_part}@{host_part}{port_part}/{postgres_db}"

 
    _LOGGER.warning("DATABASE_URL not configured")
 

DATABASE_URL = _build_database_url(BASE_DIR)
# print(f"DATABASE_URL = {DATABASE_URL}")
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "files/zip_upload_zips")
PROCESSED_DIR = BASE_DIR / os.getenv("PROCESSED_DIR", "files/zips_upload_processed")
PROCESSING_ERROR_DIR = BASE_DIR / os.getenv("PROCESSING_ERROR_DIR", "files/zip_upload_processing_error")
IMAGE_DIR = BASE_DIR / os.getenv("IMAGE_DIR", "files/zip_upload_images")
DIRECT_UPLOAD_DIR = BASE_DIR / os.getenv("DIRECT_UPLOAD_DIR", "files/direct_uploads")
PDF_DIR = BASE_DIR / os.getenv("PDF_DIR", "files/zip_upload_pdfs")
DR_PDF_DIR = BASE_DIR / os.getenv("DR_PDF_DIR", "files/dr_pdfs")
GLAUCOMA_PDF_DIR = BASE_DIR / os.getenv("GLAUCOMA_PDF_DIR", "files/glaucoma_pdfs")
SUCCESS_LOG = BASE_DIR / os.getenv("SUCCESS_LOG", "logs/process_pdf_success_log.txt")
ERROR_LOG   = BASE_DIR / os.getenv("ERROR_LOG", "logs/process_pdf_error_log.txt")
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

user_lab_units = Table(
    'user_lab_units', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True),
    Column('lab_unit_id', Integer, ForeignKey('lab_units.id', ondelete="CASCADE"), primary_key=True)
)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    year_of_joining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_date_of_service: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    file_upload_quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_upload_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # Hospital isolation fields
    hospital_id: Mapped[int | None] = mapped_column(
        ForeignKey('hospitals.id', ondelete='RESTRICT'), 
        nullable=True,
        index=True
    )
    is_master_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Relationships
    hospital: Mapped[Optional["Hospital"]] = relationship("Hospital", foreign_keys=[hospital_id])
    roles: Mapped[List["Role"]] = relationship("Role", secondary="user_roles", back_populates="users", lazy="selectin")
    lab_units: Mapped[List["LabUnit"]] = relationship("LabUnit", secondary=user_lab_units, back_populates="users")
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        foreign_keys="Notification.recipient_user_id",
        back_populates="recipient",
        lazy="selectin",
    )
    sent_notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        foreign_keys="Notification.sender_user_id",
        back_populates="sender",
        lazy="selectin",
    )
    mobile_auth_sessions: Mapped[List["MobileAuthSession"]] = relationship(
        "MobileAuthSession",
        back_populates="user",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    @property
    def is_authenticated(self) -> bool: return bool(self.is_active)
    @property
    def is_anonymous(self) -> bool: return False
    def get_id(self) -> str: return str(self.id)
    def has_role(self, *names: str) -> bool:
        # Log stack trace for debugging role checks in debug mode
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        if runtime_logger.isEnabledFor(logging.DEBUG):
            from utils.stack_trace_handler import log_current_stack
            log_current_stack(f"Checking roles {names} for user '{self.username}'")
        
        user_roles = {r.name.lower() for r in (self.roles or [])}
        result = any(n.lower() in user_roles for n in names)
        
        # Log the result in debug mode
        if runtime_logger.isEnabledFor(logging.DEBUG):
            runtime_logger.debug(
                "Role check result for user '%s': %s",
                sanitize_log_value(self.username),
                sanitize_log_value(result),
            )
        
        return result
    def has_all_roles(self, *names: str) -> bool:
        # Log stack trace for debugging role checks in debug mode
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        if runtime_logger.isEnabledFor(logging.DEBUG):
            from utils.stack_trace_handler import log_current_stack
            log_current_stack(f"Checking all roles {names} for user '{self.username}'")
        
        user_roles = {r.name.lower() for r in (self.roles or [])}
        result = all(n.lower() in user_roles for n in names)
        
        # Log the result in debug mode
        if runtime_logger.isEnabledFor(logging.DEBUG):
            runtime_logger.debug(
                "All roles check result for user '%s': %s",
                sanitize_log_value(self.username),
                sanitize_log_value(result),
            )
        
        return result

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    users: Mapped[List["User"]] = relationship("User", secondary="user_roles", back_populates="roles")

class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"), Index("ix_user_roles_user", "user_id"), Index("ix_user_roles_role", "role_id"))

class S3Config(Base):
    """
    Multi-Tenant S3-Compatible Storage Configuration

    Each hospital can have its own S3-compatible bucket configuration.
    - One active config per hospital (enforced by unique constraint)
    - Provider support: R2, Hetzner, AWS, GCP, Azure, MinIO, Other
    - Credentials encrypted with hospital-specific PyNaCl keys
    - URL signing pepper for HMAC-based access control
    - Auto-rotation support with timezone-aware scheduling
    - Binary fallback policy: never (fail hard) or always (allow local)
    """
    __tablename__ = "s3_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Hospital scoping (one active S3 config per hospital)
    hospital_id: Mapped[int] = mapped_column(
        ForeignKey("hospitals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    # Provider selection
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="other",
        server_default="other"
    )
    # Values: 'r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other'

    # S3-compatible storage details
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # S3 addressing style: virtual (vhost/bucket.endpoint.com) or path (endpoint.com/bucket)
    # Default: auto (let boto3 decide based on endpoint/bucket)
    addressing_style: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="auto",
        server_default="auto"
    )  # Values: 'auto', 'virtual', 'path'

    # Encrypted credentials (PyNaCl with hospital-specific derived key)
    access_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # URL signing (PyNaCl encrypted)
    url_signing_pepper: Mapped[str] = mapped_column(Text, nullable=False)
    url_signing_pepper_previous: Mapped[str | None] = mapped_column(Text, nullable=True)
    pepper_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Auto-rotation settings
    auto_rotate_pepper: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    rotation_time: Mapped[str | None] = mapped_column(String(8), nullable=True)  # TIME type: HH:MM:SS
    rotation_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rotation_last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Fallback policy (binary: never/always)
    fallback_policy: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="never",
        server_default="never"
    )

    # Local cleanup policy
    cleanup_local_after_s3: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false"
    )  # If True, delete local files after S3 upload confirmed

    # Status flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, server_default="false")

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Relationships
    hospital: Mapped["Hospital"] = relationship(foreign_keys=[hospital_id])
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])

    __table_args__ = (
        # Unique name per hospital
        UniqueConstraint("hospital_id", "name", name="uq_s3_config_hospital_name"),
        # Only one active config per hospital
        Index("ix_s3_config_active_per_hospital", "hospital_id", unique=True,
              postgresql_where=text("is_active = TRUE")),
        # Check constraints
        CheckConstraint("NOT (is_active = TRUE AND is_archived = TRUE)",
                       name="ck_s3_config_not_active_and_archived"),
        CheckConstraint("fallback_policy IN ('never', 'always')",
                       name="ck_s3_config_fallback_policy"),
        CheckConstraint("provider IN ('r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other')",
                       name="ck_s3_config_provider"),
        CheckConstraint("addressing_style IN ('auto', 'virtual', 'path')",
                       name="ck_s3_config_addressing_style"),
        # Indexes
        Index("ix_s3_configs_hospital_id", "hospital_id"),
        Index("ix_s3_configs_active", "hospital_id", "is_active",
              postgresql_where=text("is_active = TRUE")),
        Index("ix_s3_configs_auto_rotate", "auto_rotate_pepper", "rotation_last_run",
              postgresql_where=text("auto_rotate_pepper = TRUE")),
    )

class S3SyncStatus(Base):
    """
    S3 Sync Status Tracking

    Tracks the synchronization status of files to S3 storage.
    Supports retry logic and provides visibility into sync operations.
    """
    __tablename__ = 's3_sync_status'

    id: Mapped[int] = mapped_column(primary_key=True)

    # File reference (polymorphic - points to different tables)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Values: 'encounter_file', 'encounter_file_pdf', 'direct_upload', 'encounter_set_image'
    file_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # S3 config reference
    s3_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("s3_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Sync status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        default='pending'
    )  # pending, in_progress, success, failed

    variant: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default='original'
    )  # original, thumbnail, edited, edited_thumbnail

    # Retry tracking
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False
    )

    s3_config: Mapped["S3Config"] = relationship(foreign_keys=[s3_config_id])

    __table_args__ = (
        # Ensure one status record per file variant
        UniqueConstraint('file_type', 'file_id', 'variant', name='uq_s3_sync_file_variant'),
        # Validate status values
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'success', 'failed')",
            name='ck_s3_sync_status'
        ),
        # Validate variant values
        CheckConstraint(
            "variant IN ('original', 'thumbnail', 'edited', 'edited_thumbnail')",
            name='ck_s3_sync_variant'
        ),
        # Indexes for dashboard queries
        Index('ix_s3_sync_status_config', 's3_config_id', 'status'),
        Index('ix_s3_sync_status_created', 's3_config_id', 'status', 'created_at'),
        Index('ix_s3_sync_file_type_id', 'file_type', 'file_id'),
    )

class Hospital(Base):
    __tablename__ = 'hospitals'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    lab_units: Mapped[List["LabUnit"]] = relationship(back_populates="hospital", lazy="selectin", cascade="all, delete-orphan")

class LabUnit(Base):
    __tablename__ = 'lab_units'
    __table_args__ = (UniqueConstraint("name", "hospital_id", name="uq_labunit_name_per_hospital"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hospital_id: Mapped[int] = mapped_column(ForeignKey('hospitals.id'), nullable=False)
    hospital: Mapped["Hospital"] = relationship(back_populates="lab_units", lazy="selectin")
    users: Mapped[List["User"]] = relationship("User", secondary=user_lab_units, back_populates="lab_units", lazy="selectin")

class Camera(Base):
    __tablename__ = 'cameras'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_zip_upload_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        server_default="false",
    )

class Disease(Base):
    __tablename__ = 'diseases'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    grading_scope: Mapped[str] = mapped_column(String(20), default="image", server_default="image", nullable=False)
    remidio_ocr_linkage: Mapped[str] = mapped_column(String(32), default="none", server_default="none", nullable=False)
    disease_gradings: Mapped[List["DiseaseGrading"]] = relationship("DiseaseGrading", back_populates="disease")
    ai_model_links: Mapped[List["AIModelDisease"]] = relationship(
        "AIModelDisease",
        back_populates="disease",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint("grading_scope IN ('image', 'encounter')", name="ck_disease_grading_scope"),
        CheckConstraint(
            "remidio_ocr_linkage IN ('none', 'dr', 'amd', 'glaucoma')",
            name="ck_disease_remidio_ocr_linkage",
        ),
    )

class Area(Base):
    __tablename__ = 'areas'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class Project(Base):
    """Upload provenance project for intake authorization and governance."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    investigators: Mapped[List["ProjectInvestigator"]] = relationship(
        "ProjectInvestigator",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    upload_profile_mappings: Mapped[List["ProjectUploadProfile"]] = relationship(
        "ProjectUploadProfile",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    referral_diseases: Mapped[List["ProjectReferralDisease"]] = relationship(
        "ProjectReferralDisease",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    __table_args__ = (
        UniqueConstraint("title", name="uq_projects_title"),
        UniqueConstraint("code", name="uq_projects_code"),
        Index("ix_projects_active", "active"),
    )


class ProjectReferralDisease(Base):
    """A disease a project may record as referral-positive without grading it."""

    __tablename__ = "project_referral_diseases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disease_id: Mapped[int] = mapped_column(
        ForeignKey("diseases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="referral_diseases")
    disease: Mapped["Disease"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint("project_id", "disease_id", name="uq_project_referral_disease"),
        Index("ix_project_referral_diseases_project_active", "project_id", "active"),
    )


class ProjectInvestigator(Base):
    """Project governance membership; this does not grant upload permission."""

    __tablename__ = "project_investigators"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="investigators")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "role", name="uq_project_investigator_role"),
        CheckConstraint(
            "role IN ('principal_investigator','co_investigator','coordinator','collaborator')",
            name="ck_project_investigator_role",
        ),
        Index("ix_project_investigators_project_active", "project_id", "active"),
        Index("ix_project_investigators_user_active", "user_id", "active"),
    )


class RemidioConnection(Base):
    """Encrypted Remidio API account configuration."""

    __tablename__ = "remidio_connections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    client_name: Mapped[str] = mapped_column(String(100), nullable=False)
    client_identification_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    email_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    secret_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_auth_token_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    project: Mapped["Project | None"] = relationship("Project")
    sites: Mapped[List["RemidioSite"]] = relationship(
        "RemidioSite",
        back_populates="connection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    routing_rules: Mapped[List["RemidioRoutingRule"]] = relationship(
        "RemidioRoutingRule",
        back_populates="connection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_remidio_connections_name"),
        Index("ix_remidio_connections_project_active", "project_id", "active"),
    )


class RemidioSite(Base):
    """Remidio geographic/screening site synced from getSites plus manual custom id."""

    __tablename__ = "remidio_sites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remidio_connection_id: Mapped[int] = mapped_column(ForeignKey("remidio_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    remidio_site_id: Mapped[str] = mapped_column(String(64), nullable=False)
    site_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site_custom_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    connection: Mapped["RemidioConnection"] = relationship("RemidioConnection", back_populates="sites")
    routing_rules: Mapped[List["RemidioRoutingRule"]] = relationship("RemidioRoutingRule", back_populates="site", lazy="selectin")
    exams: Mapped[List["RemidioExam"]] = relationship("RemidioExam", back_populates="site", lazy="noload")

    __table_args__ = (
        UniqueConstraint("remidio_connection_id", "remidio_site_id", name="uq_remidio_site_connection_site_id"),
        UniqueConstraint("remidio_connection_id", "site_custom_identifier", name="uq_remidio_site_connection_custom_identifier"),
        Index("ix_remidio_sites_connection_active", "remidio_connection_id", "active"),
    )


class RemidioRoutingRule(Base):
    """Maps Remidio site/device feeds into EyeImageManager project intake metadata."""

    __tablename__ = "remidio_routing_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remidio_connection_id: Mapped[int] = mapped_column(ForeignKey("remidio_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    remidio_site_id: Mapped[int | None] = mapped_column(ForeignKey("remidio_sites.id", ondelete="SET NULL"), nullable=True, index=True)
    site_custom_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    remidio_device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id", ondelete="RESTRICT"), nullable=False, index=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False, index=True)
    default_disease_id: Mapped[int | None] = mapped_column(ForeignKey("diseases.id", ondelete="RESTRICT"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    connection: Mapped["RemidioConnection"] = relationship("RemidioConnection", back_populates="routing_rules")
    site: Mapped["RemidioSite | None"] = relationship("RemidioSite", back_populates="routing_rules")
    project: Mapped["Project"] = relationship("Project")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")
    camera: Mapped["Camera"] = relationship("Camera")
    default_disease: Mapped["Disease | None"] = relationship("Disease")

    __table_args__ = (
        UniqueConstraint(
            "remidio_connection_id",
            "site_custom_identifier",
            "remidio_device_type",
            "project_id",
            "lab_unit_id",
            "camera_id",
            name="uq_remidio_routing_rule_target",
        ),
        Index("ix_remidio_routing_connection_site_device", "remidio_connection_id", "site_custom_identifier", "remidio_device_type"),
        Index("ix_remidio_routing_project_active", "project_id", "active"),
    )


class RemidioExam(Base):
    """Remidio exam metadata pulled from gateway endpoints."""

    __tablename__ = "remidio_exams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remidio_connection_id: Mapped[int] = mapped_column(ForeignKey("remidio_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    remidio_site_id: Mapped[int | None] = mapped_column(ForeignKey("remidio_sites.id", ondelete="SET NULL"), nullable=True, index=True)
    patient_encounter_id: Mapped[int | None] = mapped_column(ForeignKey("patient_encounters.id", ondelete="SET NULL"), nullable=True, index=True)
    remidio_exam_id: Mapped[str] = mapped_column(String(64), nullable=False)
    site_custom_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    remidio_numeric_site_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    remidio_patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    remidio_patient_mrn: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    exam_local_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exam_custom_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    exam_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exam_date_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    exam_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    pull_source: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pulled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    connection: Mapped["RemidioConnection"] = relationship("RemidioConnection")
    site: Mapped["RemidioSite | None"] = relationship("RemidioSite", back_populates="exams")
    patient_encounter: Mapped["PatientEncounters | None"] = relationship("PatientEncounters")
    images: Mapped[List["RemidioImage"]] = relationship(
        "RemidioImage",
        back_populates="exam",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    reports: Mapped[List["RemidioReport"]] = relationship(
        "RemidioReport",
        back_populates="exam",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("remidio_connection_id", "remidio_exam_id", name="uq_remidio_exam_connection_exam_id"),
        UniqueConstraint("patient_encounter_id", name="uq_remidio_exam_patient_encounter_id"),
        Index("ix_remidio_exams_connection_date", "remidio_connection_id", "exam_date"),
        Index("ix_remidio_exams_connection_patient", "remidio_connection_id", "remidio_patient_mrn"),
    )


class RemidioImage(Base):
    """Image/file metadata scoped to one local RemidioExam row."""

    __tablename__ = "remidio_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remidio_exam_id: Mapped[int] = mapped_column(ForeignKey("remidio_exams.id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_file_id: Mapped[int | None] = mapped_column(ForeignKey("encounter_files.id", ondelete="SET NULL"), nullable=True, index=True)
    encounter_set_image_id: Mapped[int | None] = mapped_column(ForeignKey("encounter_set_images.id", ondelete="SET NULL"), nullable=True, index=True)
    remidio_image_id: Mapped[str] = mapped_column(String(64), nullable=False)
    device_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    image_bucket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_variant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    laterality: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    field: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    quality: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remidio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    remidio_thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    exam: Mapped["RemidioExam"] = relationship("RemidioExam", back_populates="images")
    encounter_file: Mapped["EncounterFile | None"] = relationship("EncounterFile")
    encounter_set_image: Mapped["EncounterSetImage | None"] = relationship("EncounterSetImage")

    __table_args__ = (
        UniqueConstraint("remidio_exam_id", "remidio_image_id", name="uq_remidio_image_exam_image_id"),
        Index("ix_remidio_images_exam_device", "remidio_exam_id", "device_type"),
    )


class RemidioReport(Base):
    """Report/PDF/AI report metadata scoped to one local RemidioExam row."""

    __tablename__ = "remidio_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remidio_exam_id: Mapped[int] = mapped_column(ForeignKey("remidio_exams.id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_file_pdf_id: Mapped[int | None] = mapped_column(ForeignKey("encounter_file_pdfs.id", ondelete="SET NULL"), nullable=True, index=True)
    encounter_set_attachment_id: Mapped[int | None] = mapped_column(ForeignKey("encounter_set_attachments.id", ondelete="SET NULL"), nullable=True, index=True)
    remidio_report_id: Mapped[str] = mapped_column(String(64), nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    report_local_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_date_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remidio_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    exam: Mapped["RemidioExam"] = relationship("RemidioExam", back_populates="reports")
    encounter_file_pdf: Mapped["EncounterFilePDF | None"] = relationship("EncounterFilePDF")
    encounter_set_attachment: Mapped["EncounterSetAttachment | None"] = relationship("EncounterSetAttachment")

    __table_args__ = (
        UniqueConstraint("remidio_exam_id", "remidio_report_id", "report_type", name="uq_remidio_report_exam_report_type"),
        Index("ix_remidio_reports_exam_type", "remidio_exam_id", "report_type"),
    )


class DiseaseGrading(Base):
    __tablename__ = 'disease_gradings'
    id: Mapped[int] = mapped_column(primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id'), nullable=False)
    impression: Mapped[str] = mapped_column(String(64), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    prioritize_for_task_selection: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_ungradable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    guidelines: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disease: Mapped["Disease"] = relationship("Disease", back_populates="disease_gradings")
    features: Mapped[List["GradingsFeatures"]] = relationship("GradingsFeatures", back_populates="disease_grading", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint('disease_id', 'impression', name='uq_disease_grading_disease_impression'),
        Index('ix_disease_gradings_disease_order', 'disease_id', 'display_order'),
    )


class LinkedDiseaseGrading(Base):
    __tablename__ = "linked_disease_gradings"

    id: Mapped[int] = mapped_column(primary_key=True)
    primary_disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False, index=True)
    linked_disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    primary_disease: Mapped["Disease"] = relationship("Disease", foreign_keys=[primary_disease_id])
    linked_disease: Mapped["Disease"] = relationship("Disease", foreign_keys=[linked_disease_id])

    __table_args__ = (
        UniqueConstraint("primary_disease_id", "linked_disease_id", name="uq_linked_disease_pair"),
        UniqueConstraint("linked_disease_id", name="uq_linked_disease_unique"),
        CheckConstraint("primary_disease_id <> linked_disease_id", name="ck_linked_disease_not_self"),
        Index("ix_linked_disease_primary_active", "primary_disease_id", "is_active"),
    )


class GradingsFeatures(Base):
    __tablename__ = 'gradings_features'
    id: Mapped[int] = mapped_column(primary_key=True)
    disease_grading_id: Mapped[int] = mapped_column(ForeignKey('disease_gradings.id', ondelete='CASCADE'), nullable=False, index=True)
    sr_no: Mapped[int] = mapped_column(Integer, nullable=False)  # Display order
    label: Mapped[str] = mapped_column(String(255), nullable=False)  # Feature name
    disease_grading: Mapped["DiseaseGrading"] = relationship("DiseaseGrading", back_populates="features")
    
    __table_args__ = (
        UniqueConstraint('disease_grading_id', 'sr_no', name='uq_gradings_features_order'),
        Index('ix_gradings_features_grading_order', 'disease_grading_id', 'sr_no'),
    )


class ZipFile(Base):
    __tablename__ = 'zip_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    zip_filename: Mapped[str] = mapped_column(unique=True)
    md5_hash: Mapped[str] = mapped_column(unique=True)
    upload_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date())
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="zip_file", uselist=False, cascade="all, delete-orphan")

class PatientEncounters(Base):
    __tablename__ = 'patient_encounters'
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid4()))
    zip_file_id: Mapped[int | None] = mapped_column(ForeignKey('zip_files.id'), unique=True, nullable=True)
    is_set_based: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    name: Mapped[str]
    patient_id: Mapped[str]
    capture_date: Mapped[str]
    glaucoma_verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    glaucoma_verified_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    glaucoma_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dr_verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    dr_verified_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    dr_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capture_date_dt: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    lab_unit_id: Mapped[int | None] = mapped_column(ForeignKey('lab_units.id'), nullable=True, index=True)
    encounter_verified_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    encounter_verified_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    encounter_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disease_id: Mapped[int | None] = mapped_column(ForeignKey('diseases.id'), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    upload_profile_id: Mapped[int | None] = mapped_column(ForeignKey("upload_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    referral_suggestion: Mapped[str] = mapped_column(String(16), nullable=False, default="missing", server_default="missing", index=True)
    referral_suggestion_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referral_positive_diseases_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    zip_file: Mapped["ZipFile"] = relationship(back_populates="patient_encounter")
    encounter_files: Mapped[List["EncounterFile"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    encounter_set_images: Mapped[List["EncounterSetImage"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    encounter_set_attachments: Mapped[List["EncounterSetAttachment"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    encounter_file_pdfs: Mapped[List["EncounterFilePDF"]] = relationship(cascade="all, delete-orphan")
    dr_reports: Mapped[List["DiabeticRetinopathyReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    amd_reports: Mapped[List["AMDReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    glaucoma_reports: Mapped[List["GlaucomaReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    glaucoma_results_cleaned: Mapped[List["GlaucomaResultsCleaned"]] = relationship()
    lab_unit: Mapped["LabUnit"] = relationship()
    project: Mapped["Project | None"] = relationship("Project")
    upload_profile: Mapped["UploadProfile | None"] = relationship("UploadProfile")

    __table_args__ = (
        CheckConstraint(
            "referral_suggestion IN ('yes','no','missing')",
            name="ck_patient_encounters_referral_suggestion",
        ),
    )

class EncounterSetImage(Base):
    __tablename__ = 'encounter_set_images'
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid4()))
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id', ondelete='CASCADE'), index=True)
    spatial_position: Mapped[int] = mapped_column(Integer, nullable=False) # 1-9
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    edited_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    thumbnail_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    folder_rel: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    asset_kind: Mapped[str] = mapped_column(String(32), default="clinical_image", nullable=False, server_default="clinical_image")
    creates_task: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    visible_to_grader: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # Verification and PII masking fields
    is_anonymized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_not_gradable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    not_gradable_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # S3 storage fields (nullable - NULL = local storage, non-NULL = S3 storage)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    is_mydriatic: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    referral_needed_or_positive_image: Mapped[str] = mapped_column(String(16), nullable=False, default="missing", server_default="missing", index=True)
    referral_needed_or_positive_image_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True, index=True)
    s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for original
    s3_object_key_edited: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for edited
    s3_object_key_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for thumbnail

    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_set_images")
    project: Mapped["Project | None"] = relationship("Project")
    camera: Mapped["Camera | None"] = relationship("Camera")
    area: Mapped["Area | None"] = relationship("Area")
    s3_config: Mapped["S3Config"] = relationship(foreign_keys=[s3_config_id])

    __table_args__ = (
        UniqueConstraint('patient_encounter_id', 'spatial_position', name='uq_encounter_set_image_position'),
        CheckConstraint('spatial_position >= 1', name='ck_encounter_set_image_position_positive'),
        CheckConstraint("asset_kind = 'clinical_image'", name="ck_encounter_set_image_asset_kind"),
        CheckConstraint(
            "referral_needed_or_positive_image IN ('yes','no','missing')",
            name="ck_encounter_set_images_referral_needed_or_positive_image",
        ),
        # S3 composite indexes for efficient queries
        Index("ix_esi_s3_config_uuid", "s3_config_id", "uuid"),
        Index("ix_esi_hospital_id", "hospital_id"),
        Index("ix_esi_task_evidence", "patient_encounter_id", "asset_kind", "creates_task", "visible_to_grader"),
    )

class EncounterFile(Base):
    __tablename__ = 'encounter_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    filename: Mapped[str]
    file_type: Mapped[str]
    ocr_processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    eye_side: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    centering: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    lab_unit_id: Mapped[int | None] = mapped_column(ForeignKey('lab_units.id'), nullable=True, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey('cameras.id'), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    thumbnail_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # thumbnail basename (thm_uuid.ext)

    # S3 storage fields (nullable - NULL = local storage, non-NULL = S3 storage)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True, index=True)
    s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True, index=True)
    s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for image
    s3_object_key_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for thumbnail

    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_files")
    lab_unit: Mapped["LabUnit"] = relationship()
    camera: Mapped["Camera | None"] = relationship()
    project: Mapped["Project | None"] = relationship("Project")
    s3_config: Mapped["S3Config"] = relationship(foreign_keys=[s3_config_id])
    # Note: ImageGrading relationship removed - now using Grade model through GradingTask
    # Add a check constraint to ensure only image files are stored in this table
    __table_args__ = (
        CheckConstraint("file_type != 'pdf'", name="ck_encounter_file_not_pdf"),
        CheckConstraint("thumbnail_filename IS NULL OR position('/' in thumbnail_filename) = 0", name="ck_ef_thumbnail_filename_no_slash"),
        # S3 composite indexes for efficient queries
        Index("ix_ef_s3_config_uuid", "s3_config_id", "uuid"),
        Index("ix_ef_hospital_id", "hospital_id"),
    )

class EncounterFilePDF(Base):
    __tablename__ = 'encounter_file_pdfs'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    filename: Mapped[str]
    file_type: Mapped[str] = mapped_column(String(16), default='pdf')
    ocr_processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    eye_side: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    lab_unit_id: Mapped[int | None] = mapped_column(ForeignKey('lab_units.id'), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)

    # S3 storage fields (nullable - NULL = local storage, non-NULL = S3 storage)
    hospital_id: Mapped[int | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True, index=True)
    s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True, index=True)
    s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for PDF

    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_file_pdfs")
    lab_unit: Mapped["LabUnit"] = relationship()
    project: Mapped["Project | None"] = relationship("Project")
    s3_config: Mapped["S3Config"] = relationship(foreign_keys=[s3_config_id])

    # Add a check constraint to ensure only PDF files are stored in this table
    __table_args__ = (
        CheckConstraint("file_type = 'pdf'", name="ck_encounter_file_pdf_only"),
        Index('ix_encounter_file_pdfs_patient_encounter_id', 'patient_encounter_id'),
        # S3 composite indexes for efficient queries
        Index("ix_efpdf_s3_config_uuid", "s3_config_id", "uuid"),
        Index("ix_efpdf_hospital_id", "hospital_id"),
    )

class DiabeticRetinopathyReport(Base):
    __tablename__ = 'diabetic_retinopathy_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    result: Mapped[str]
    qualitative_result: Mapped[str | None] = mapped_column(nullable=True)
    report_file_name: Mapped[str | None] = mapped_column(nullable=True)
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="dr_reports")

class AMDReport(Base):
    __tablename__ = 'amd_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'), index=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    result: Mapped[str | None] = mapped_column(nullable=True)
    qualitative_result: Mapped[str | None] = mapped_column(nullable=True)
    report_file_name: Mapped[str | None] = mapped_column(nullable=True)
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="amd_reports")

class GlaucomaReport(Base):
    __tablename__ = 'glaucoma_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    vcdr_right: Mapped[str | None]
    vcdr_left: Mapped[str | None]
    result: Mapped[str]
    qualitative_result: Mapped[str | None] = mapped_column(nullable=True)
    report_file_name: Mapped[str | None] = mapped_column(nullable=True)
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="glaucoma_reports")

class GlaucomaResultsCleaned(Base):
    __tablename__ = 'glaucoma_results_cleaned'
    id: Mapped[int] = mapped_column(primary_key=True)
    glaucoma_report_id: Mapped[int] = mapped_column(ForeignKey('glaucoma_reports.id'), unique=True, index=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'), index=True)
    vcdr_right_num: Mapped[float | None] = mapped_column(nullable=True)
    vcdr_left_num: Mapped[float | None] = mapped_column(nullable=True)
    original_vcdr_right: Mapped[str | None] = mapped_column(nullable=True)
    original_vcdr_left: Mapped[str | None] = mapped_column(nullable=True)
    result: Mapped[str | None] = mapped_column(nullable=True)
    qualitative_result: Mapped[str | None] = mapped_column(nullable=True)
    report_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    report_file_name: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="glaucoma_results_cleaned")
    glaucoma_report: Mapped["GlaucomaReport"] = relationship("GlaucomaReport")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="queued")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejected_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    excel_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    upload_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    upload_kind: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    upload_profile_id: Mapped[int | None] = mapped_column(ForeignKey("upload_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    uploader_username: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    uploader_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lab_unit_id: Mapped[int | None] = mapped_column(ForeignKey("lab_units.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    items: Mapped[List["JobItem"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")
    project: Mapped["Project | None"] = relationship("Project")
    upload_profile: Mapped["UploadProfile | None"] = relationship("UploadProfile")
    __table_args__ = (
        Index(
            "uq_jobs_uploader_idempotency_key",
            "uploader_user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

class JobItem(Base):
    __tablename__ = "job_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    filename: Mapped[str]
    state: Mapped[str] = mapped_column(default="queued")
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    uploader_username: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    uploader_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    job: Mapped["Job"] = relationship(back_populates="items")


class TaskBackfillJob(Base):
    __tablename__ = "task_backfill_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    requested_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_candidates: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_by_username: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)
    hospital_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hospitals.id"), nullable=True, index=True)
    allowed_lab_unit_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_task_backfill_job_status",
        ),
        Index("ix_task_backfill_jobs_hospital_created", "hospital_id", "created_at"),
    )

    created_by: Mapped["User"] = relationship("User")
    hospital: Mapped["Hospital"] = relationship("Hospital")


class ImageMetadataBackfillJob(Base):
    __tablename__ = "image_metadata_backfill_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    requested_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_metadata: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    run_pii: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pii_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_candidates: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_by_username: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)
    hospital_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hospitals.id"), nullable=True, index=True)
    allowed_lab_unit_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_image_metadata_backfill_job_status",
        ),
        Index("ix_image_metadata_backfill_jobs_hospital_created", "hospital_id", "created_at"),
    )

    created_by: Mapped["User"] = relationship("User")
    hospital: Mapped["Hospital"] = relationship("Hospital")


class PiiDetectionJob(Base):
    __tablename__ = "pii_detection_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    image_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    image_variant: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_pii_detection_job_status",
        ),
        CheckConstraint(
            "image_variant IN ('orig','edited')",
            name="ck_pii_detection_job_variant",
        ),
        CheckConstraint(
            "source IN ('auto','manual')",
            name="ck_pii_detection_job_source",
        ),
        Index("ix_pii_detection_jobs_status_created", "status", "created_at"),
    )


class CeleryBeatSchedule(Base):
    __tablename__ = "celery_beat_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    queue: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    schedule_type: Mapped[str] = mapped_column(String(16), nullable=False, default="interval")
    interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crontab_minute: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    crontab_hour: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    crontab_day_of_week: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    crontab_day_of_month: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    crontab_month_of_year: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    hospital_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hospitals.id"), nullable=True, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    __table_args__ = (
        CheckConstraint(
            "schedule_type IN ('interval','crontab')",
            name="ck_celery_beat_schedule_type",
        ),
        CheckConstraint(
            "(schedule_type = 'interval' AND interval_seconds IS NOT NULL) "
            "OR (schedule_type = 'crontab' AND interval_seconds IS NULL)",
            name="ck_celery_beat_schedule_interval_consistency",
        ),
        Index("ix_celery_beat_enabled_type", "enabled", "schedule_type"),
    )

    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
    hospital: Mapped[Optional["Hospital"]] = relationship("Hospital", foreign_keys=[hospital_id])
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_id])



class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username_input: Mapped[str] = mapped_column(String(150), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    __table_args__ = (Index("ix_login_attempts_username_created", "username_input", "created_at"), Index("ix_login_attempts_ip_created", "ip_address", "created_at"))

class IpLock(Base):
    __tablename__ = "ip_locks"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip_address: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("ip_address", name="uq_iplock_ip"),)


class PasswordResetAttempt(Base):
    __tablename__ = "password_reset_attempts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    __table_args__ = (
        Index("ix_password_reset_attempts_email_date", "email", "attempted_at"), 
        Index("ix_password_reset_attempts_ip_date", "ip_address", "attempted_at"))




# --- Direct Image Upload Table ---
class DirectImageUpload(Base):
    __tablename__ = "direct_image_uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid4()))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)          # original file name (basename)
    edited_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # edited basename (under <folder_rel>/edited/)
    folder_rel: Mapped[str] = mapped_column(String(512), nullable=False, index=True) # POSIX-style relative directory from BASE_DIR (e.g., "files/direct_uploads/2025_09_01_user7")
    file_hash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id"), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), nullable=False)
    is_mydriatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pregraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # thumbnail basename (thm_uuid.ext)
    edited_thumbnail_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # edited thumbnail basename (thm_uuid.ext)

    # S3 storage fields (nullable - NULL = local storage, non-NULL = S3 storage)
    s3_config_id: Mapped[int | None] = mapped_column(ForeignKey("s3_configs.id"), nullable=True, index=True)
    s3_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for original
    s3_object_key_edited: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for edited
    s3_object_key_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for thumbnail
    s3_object_key_edited_thumbnail: Mapped[str | None] = mapped_column(String(500), nullable=True)  # S3 object key for edited thumbnail

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    # Relationships
    uploader: Mapped["User"] = relationship(foreign_keys=[uploader_id])
    hospital: Mapped["Hospital"] = relationship()
    lab_unit: Mapped["LabUnit"] = relationship()
    project: Mapped["Project | None"] = relationship("Project")
    camera: Mapped["Camera"] = relationship()
    disease: Mapped["Disease"] = relationship()
    area: Mapped["Area"] = relationship()
    s3_config: Mapped["S3Config"] = relationship(foreign_keys=[s3_config_id])

    __table_args__ = (
        # Basename only (no slashes) - use PostgreSQL compatible functions
        CheckConstraint("position('/' in filename) = 0", name="ck_diu_filename_no_slash"),
        CheckConstraint(
            "edited_filename IS NULL OR position('/' in edited_filename) = 0",
            name="ck_diu_edited_filename_no_slash",
        ),
        CheckConstraint(
            "thumbnail_filename IS NULL OR position('/' in thumbnail_filename) = 0",
            name="ck_diu_thumbnail_filename_no_slash",
        ),
        CheckConstraint(
            "edited_thumbnail_filename IS NULL OR position('/' in edited_thumbnail_filename) = 0",
            name="ck_diu_edited_thumbnail_filename_no_slash",
        ),
        # folder_rel should be a relative POSIX path (no leading '/', no backslashes)
        CheckConstraint("substring(folder_rel, 1, 1) <> '/'", name="ck_diu_folder_not_absolute"),
        CheckConstraint("position('\\\\' in folder_rel) = 0", name="ck_diu_folder_no_backslash"),
        # Helpful composite indexes
        Index("ix_diu_uploader_created", "uploader_id", "created_at"),
        Index("ix_diu_folder_created", "folder_rel", "created_at"),
        Index("ix_diu_content_hash", "content_hash"),
        Index("ix_diu_is_pregraded", "is_pregraded"),
        # S3 composite indexes for efficient queries
        Index("ix_diu_s3_config_uuid", "s3_config_id", "uuid"),
        Index("ix_diu_s3_config_created", "s3_config_id", "created_at"),
        Index("ix_diu_hospital_id", "hospital_id"),
    )
    
    verifications: Mapped[List["DirectImageVerify"]] = relationship(back_populates="image_upload", cascade="all, delete-orphan")
    # Note: ImageGrading relationship removed - now using Grade model through GradingTask


class DirectImageVerify(Base):
    __tablename__ = "direct_image_verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    image_upload_id: Mapped[int] = mapped_column(ForeignKey("direct_image_uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    verified_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    image_upload: Mapped["DirectImageUpload"] = relationship(back_populates="verifications")
    verified_by: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("image_upload_id", name="uq_direct_image_verify_upload_id"),
        CheckConstraint("verified_status IN ('verified', 'unverified', 'pending', 'not_gradable')", name="ck_di_verify_status",),
    )


class ImagePiiVerification(Base):
    __tablename__ = "image_pii_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    image_variant: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    pii_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), default="auto", nullable=False, index=True)
    detections_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    roi_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("image_uuid", "image_variant", name="uq_image_pii_verification_uuid_variant"),
        CheckConstraint("image_variant IN ('orig', 'edited')", name="ck_pii_verification_variant"),
        CheckConstraint("pii_status IN ('detected', 'clear', 'error')", name="ck_pii_verification_status"),
        CheckConstraint("source IN ('auto', 'manual')", name="ck_pii_verification_source"),
    )


class ImageMetadata(Base):
    __tablename__ = "image_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    image_variant: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    encounter_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("encounter_files.id", ondelete="CASCADE"), nullable=True, index=True
    )
    direct_image_upload_id: Mapped[int | None] = mapped_column(
        ForeignKey("direct_image_uploads.id", ondelete="CASCADE"), nullable=True, index=True
    )
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bit_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_grayscale: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_alpha: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dpi_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    dpi_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_luminance: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_luminance: Mapped[float | None] = mapped_column(Float, nullable=True)
    luminance_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_b: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_b: Mapped[float | None] = mapped_column(Float, nullable=True)
    histogram_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    exif_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    iptc_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("image_uuid", "image_variant", name="uq_image_metadata_uuid_variant"),
        CheckConstraint("image_variant IN ('orig', 'edited')", name="ck_image_metadata_variant"),
    )


# --- Dual Grading Models ---


class AIModel(Base):
    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_ai_models_name_version"),
    )

    grades: Mapped[List["Grade"]] = relationship("Grade", back_populates="ai_model")
    disease_links: Mapped[List["AIModelDisease"]] = relationship(
        "AIModelDisease",
        back_populates="ai_model",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    integration: Mapped["AIModelIntegration | None"] = relationship(
        "AIModelIntegration",
        back_populates="ai_model",
        uselist=False,
        cascade="all, delete-orphan",
    )
    inference_runs: Mapped[List["AIInferenceRun"]] = relationship(
        "AIInferenceRun",
        back_populates="ai_model",
        cascade="all, delete-orphan",
    )


class AIModelDisease(Base):
    """Explicit disease eligibility for an AI model."""

    __tablename__ = "ai_model_diseases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id", ondelete="CASCADE"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    ai_model: Mapped["AIModel"] = relationship("AIModel", back_populates="disease_links")
    disease: Mapped["Disease"] = relationship("Disease", back_populates="ai_model_links")

    __table_args__ = (
        UniqueConstraint("ai_model_id", "disease_id", name="uq_ai_model_disease"),
        Index("ix_ai_model_diseases_disease_active", "disease_id", "active"),
    )


class AIModelIntegration(Base):
    __tablename__ = "ai_model_integrations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ai_model_id: Mapped[int] = mapped_column(
        ForeignKey("ai_models.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    bearer_token: Mapped[str] = mapped_column(Text, nullable=False)
    api_base_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    ai_model: Mapped["AIModel"] = relationship("AIModel", back_populates="integration")
    inference_runs: Mapped[List["AIInferenceRun"]] = relationship(
        "AIInferenceRun",
        back_populates="integration",
    )

    __table_args__ = (
        UniqueConstraint("provider", name="uq_ai_model_integrations_provider"),
        CheckConstraint(
            "provider IN ('wadhwani_glaucoma','wai_dr_dme')",
            name="ck_ai_model_integration_provider_valid",
        ),
    )

    def set_access_token(self, token: str) -> None:
        """Encrypt a provider token before persistence."""
        from utils.encryption import encrypt_password

        self.access_token_encrypted = encrypt_password(token)

    def get_access_token(self) -> str:
        """Decrypt the provider token only at the execution boundary."""
        from utils.encryption import decrypt_password

        if not self.access_token_encrypted:
            raise ValueError("Remote inference access token is not configured.")
        return decrypt_password(self.access_token_encrypted)


class GradingTask(Base):
    __tablename__ = 'grading_tasks'

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid4()),
    )

    # Exactly one of these must be non-null
    encounter_file_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_files.id', ondelete='CASCADE'), nullable=True, index=True)
    direct_image_upload_id: Mapped[int | None] = mapped_column(ForeignKey('direct_image_uploads.id', ondelete='CASCADE'), nullable=True, index=True)
    patient_encounter_id: Mapped[int | None] = mapped_column(ForeignKey('patient_encounters.id', ondelete='CASCADE'), nullable=True, index=True)
    encounter_set_image_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_set_images.id', ondelete='CASCADE'), nullable=True, index=True)
    encounter_set_package_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_set_grading_packages.id', ondelete='CASCADE'), nullable=True, index=True)
    encounter_set_scope_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_set_grading_scopes.id', ondelete='CASCADE'), nullable=True, index=True)
    source_upload_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey('upload_profiles.id', ondelete='SET NULL'), nullable=True, index=True
    )
    grading_target_level: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    task_source: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id'), nullable=False, index=True)
    # lab_unit_id is used strictly for grading assignment and queue scoping.
    # It does not redefine image identity; uniqueness is enforced across labs.
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey('lab_units.id'), nullable=False, index=True)

    # Owning project, resolved from whichever source row this task hangs off.
    # Maintained by the database (trigger trg_grading_tasks_apply_project_id):
    # do not assign it in application code, and do not trust an in-session value
    # before the row is flushed and refreshed. A companion guard trigger refuses
    # to move a source row to another project while tasks still reference it, so
    # this value cannot go stale.
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey('projects.id', ondelete='SET NULL'), nullable=True
    )

    state: Mapped[str] = mapped_column(String(24), default='pending', nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    # Optional linkage to an Ad-hoc batch for auditability
    ad_hoc_id: Mapped[int | None] = mapped_column(ForeignKey('ad_hoc_task_creations.id', ondelete='SET NULL'), nullable=True, index=True)

    # Relationships (no back_populates on existing models to avoid touching them)
    disease: Mapped['Disease'] = relationship('Disease', foreign_keys=[disease_id])
    lab_unit: Mapped['LabUnit'] = relationship('LabUnit', foreign_keys=[lab_unit_id])
    encounter_file: Mapped['EncounterFile'] = relationship('EncounterFile')
    direct_image: Mapped['DirectImageUpload'] = relationship('DirectImageUpload')
    patient_encounter: Mapped['PatientEncounters'] = relationship('PatientEncounters')
    encounter_set_image: Mapped['EncounterSetImage | None'] = relationship('EncounterSetImage')
    encounter_set_package: Mapped['EncounterSetGradingPackage | None'] = relationship(
        'EncounterSetGradingPackage',
        back_populates='tasks',
    )
    encounter_set_scope: Mapped['EncounterSetGradingScope | None'] = relationship(
        'EncounterSetGradingScope',
        back_populates='tasks',
        foreign_keys=[encounter_set_scope_id],
    )
    grades: Mapped[list['Grade']] = relationship('Grade', back_populates='task', cascade="all, delete-orphan")
    consensus: Mapped['Consensus | None'] = relationship(
        'Consensus', back_populates='task', uselist=False, cascade="all, delete-orphan", single_parent=True
    )
    inference_runs: Mapped[list["AIInferenceRun"]] = relationship(
        "AIInferenceRun",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    # Relationship added after class AdHocTaskCreation definition
    ad_hoc: Mapped['AdHocTaskCreation | None'] = relationship(
        'AdHocTaskCreation', back_populates='tasks', lazy='selectin'
    )

    __table_args__ = (
        # Ensure one and only one image reference is set
        CheckConstraint(
            "(encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NULL AND encounter_set_image_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL AND patient_encounter_id IS NULL AND encounter_set_image_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NOT NULL AND encounter_set_image_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NULL AND encounter_set_image_id IS NOT NULL)",
            name='ck_grading_task_source_polymorphic'
        ),
        # Unique per image/encounter×disease across all lab units
        UniqueConstraint('encounter_file_id', 'disease_id', name='uq_task_encounter_disease'),
        UniqueConstraint('direct_image_upload_id', 'disease_id', name='uq_task_direct_disease'),
        Index(
            'uq_task_package_encounter_target',
            'encounter_set_package_id',
            'patient_encounter_id',
            'disease_id',
            'grading_target_level',
            unique=True,
            postgresql_where=text(
                'encounter_set_package_id IS NOT NULL AND patient_encounter_id IS NOT NULL'
            ),
        ),
        Index(
            'uq_task_package_image_target',
            'encounter_set_package_id',
            'encounter_set_image_id',
            'disease_id',
            'grading_target_level',
            unique=True,
            postgresql_where=text(
                'encounter_set_package_id IS NOT NULL AND encounter_set_image_id IS NOT NULL'
            ),
        ),
        Index(
            'uq_task_patient_encounter_disease_unscoped',
            'patient_encounter_id',
            'disease_id',
            unique=True,
            postgresql_where=text('encounter_set_package_id IS NULL'),
        ),
        Index(
            'uq_task_encounter_set_image_disease_unscoped',
            'encounter_set_image_id',
            'disease_id',
            unique=True,
            postgresql_where=text('encounter_set_package_id IS NULL'),
        ),
        CheckConstraint(
            "state IN ('pending','resident_done','resident2_done','arbitration','final')",
            name='ck_task_state_valid'
        ),
        CheckConstraint(
            "grading_target_level IS NULL OR grading_target_level IN ('image','encounter')",
            name='ck_task_grading_target_level_valid',
        ),
        Index('ix_task_disease_lab_state', 'disease_id', 'lab_unit_id', 'state'),
    )


class EncounterSetGradingPackage(Base):
    __tablename__ = 'encounter_set_grading_packages'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid4()))
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id', ondelete='CASCADE'), nullable=False, index=True)
    upload_profile_est_grading_package_id: Mapped[int | None] = mapped_column(
        ForeignKey('upload_profile_est_grading_packages.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    encounter_set_type_id: Mapped[int | None] = mapped_column(
        ForeignKey('encounter_set_types.id', ondelete='RESTRICT'),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    applicability: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grading_mode: Mapped[str] = mapped_column(String(32), default="unified", server_default="unified", nullable=False)
    root_scope_disease_id: Mapped[int | None] = mapped_column(ForeignKey('diseases.id', ondelete='RESTRICT'), nullable=True, index=True)
    policy_schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    policy_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    record_origin: Mapped[str] = mapped_column(String(32), default="native", server_default="native", nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    resident_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    resident2_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    arbitrator_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(24), default='pending', nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    patient_encounter: Mapped['PatientEncounters'] = relationship('PatientEncounters')
    tasks: Mapped[list['GradingTask']] = relationship(
        'GradingTask',
        back_populates='encounter_set_package',
        cascade='all, delete-orphan',
        lazy='selectin',
    )
    scopes: Mapped[list['EncounterSetGradingScope']] = relationship(
        'EncounterSetGradingScope',
        back_populates='package',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='EncounterSetGradingScope.display_order',
    )
    submissions: Mapped[list['EncounterSetGradingSubmission']] = relationship(
        'EncounterSetGradingSubmission',
        back_populates='package',
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    __table_args__ = (
        UniqueConstraint('patient_encounter_id', 'code', name='uq_encounter_set_grading_package_code'),
        CheckConstraint(
            "state IN ('pending','resident_done','resident2_done','arbitration','final')",
            name='ck_encounter_set_grading_package_state',
        ),
        CheckConstraint(
            "grading_mode IN ('unified','disease_specific')",
            name='ck_encounter_set_grading_package_mode',
        ),
        CheckConstraint(
            "record_origin IN ('native','legacy_reconstructed','legacy_partial')",
            name='ck_encounter_set_grading_package_origin',
        ),
        Index('ix_esgp_encounter_state', 'patient_encounter_id', 'state'),
    )


class EncounterSetGradingScope(Base):
    """Frozen disease/set scope inside one runtime EncounterSet package."""

    __tablename__ = 'encounter_set_grading_scopes'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid4()))
    encounter_set_package_id: Mapped[int] = mapped_column(ForeignKey('encounter_set_grading_packages.id', ondelete='CASCADE'), nullable=False, index=True)
    scope_disease_id: Mapped[int | None] = mapped_column(ForeignKey('diseases.id', ondelete='RESTRICT'), nullable=True, index=True)
    image_grading_scheme_id: Mapped[int | None] = mapped_column(ForeignKey('diseases.id', ondelete='RESTRICT'), nullable=True, index=True)
    encounter_grading_scheme_id: Mapped[int] = mapped_column(ForeignKey('diseases.id', ondelete='RESTRICT'), nullable=False, index=True)
    parent_scope_disease_id: Mapped[int | None] = mapped_column(ForeignKey('diseases.id', ondelete='RESTRICT'), nullable=True, index=True)
    link_role: Mapped[str] = mapped_column(String(16), nullable=False, default='root', server_default='root')
    state: Mapped[str] = mapped_column(String(24), nullable=False, default='pending', server_default='pending', index=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    scope_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    package: Mapped['EncounterSetGradingPackage'] = relationship('EncounterSetGradingPackage', back_populates='scopes')
    tasks: Mapped[list['GradingTask']] = relationship(
        'GradingTask',
        back_populates='encounter_set_scope',
        foreign_keys='GradingTask.encounter_set_scope_id',
        lazy='selectin',
    )
    scope_disease: Mapped['Disease | None'] = relationship('Disease', foreign_keys=[scope_disease_id])
    image_grading_scheme: Mapped['Disease | None'] = relationship('Disease', foreign_keys=[image_grading_scheme_id])
    encounter_grading_scheme: Mapped['Disease'] = relationship('Disease', foreign_keys=[encounter_grading_scheme_id])

    __table_args__ = (
        UniqueConstraint('encounter_set_package_id', 'scope_disease_id', name='uq_es_grading_scope_package_disease'),
        CheckConstraint("link_role IN ('root','linked','unified')", name='ck_es_grading_scope_link_role'),
        CheckConstraint("state IN ('pending','resident_done','resident2_done','arbitration','final')", name='ck_es_grading_scope_state'),
    )


class EncounterSetGradingSubmission(Base):
    """Immutable package or scope submission audit event."""

    __tablename__ = 'encounter_set_grading_submissions'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid4()))
    encounter_set_package_id: Mapped[int] = mapped_column(ForeignKey('encounter_set_grading_packages.id', ondelete='CASCADE'), nullable=False, index=True)
    grader_user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, index=True)
    role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    submission_kind: Mapped[str] = mapped_column(String(16), nullable=False, default='initial', server_default='initial')
    package_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')
    source: Mapped[str] = mapped_column(String(32), nullable=False, default='native', server_default='native')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    package: Mapped['EncounterSetGradingPackage'] = relationship('EncounterSetGradingPackage', back_populates='submissions')
    grader: Mapped['User'] = relationship('User')
    items: Mapped[list['EncounterSetGradingSubmissionItem']] = relationship(
        'EncounterSetGradingSubmissionItem',
        back_populates='submission',
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    __table_args__ = (
        CheckConstraint("role_slot IN ('resident','resident2','arbitrator')", name='ck_es_grading_submission_role'),
        CheckConstraint("submission_kind IN ('initial','revision','legacy_import')", name='ck_es_grading_submission_kind'),
        CheckConstraint("source IN ('native','legacy_backfill')", name='ck_es_grading_submission_source'),
    )


class EncounterSetGradingSubmissionItem(Base):
    """Immutable value snapshot for one target in a package submission."""

    __tablename__ = 'encounter_set_grading_submission_items'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey('encounter_set_grading_submissions.id', ondelete='CASCADE'), nullable=False)
    encounter_set_scope_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_set_grading_scopes.id', ondelete='SET NULL'), nullable=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('grading_tasks.id', ondelete='RESTRICT'), nullable=False)
    grade_id: Mapped[int | None] = mapped_column(ForeignKey('grades.id', ondelete='SET NULL'), nullable=True)
    target_level: Mapped[str] = mapped_column(String(24), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_disease_id: Mapped[int | None] = mapped_column(ForeignKey('diseases.id', ondelete='SET NULL'), nullable=True)
    scope_disease_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disease_grading_id: Mapped[int] = mapped_column(ForeignKey('disease_gradings.id', ondelete='RESTRICT'), nullable=False)
    grade_name: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_geometry_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    target_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    submission: Mapped['EncounterSetGradingSubmission'] = relationship('EncounterSetGradingSubmission', back_populates='items')

    __table_args__ = (
        UniqueConstraint('submission_id', 'task_id', name='uq_es_grading_submission_item_task'),
        CheckConstraint("target_level IN ('image','encounter')", name='ck_es_grading_submission_item_target'),
        CheckConstraint("scope_kind IN ('encounter_set_unified','encounter_set_disease')", name='ck_es_grading_submission_item_scope'),
        Index('ix_esgsi_submission', 'submission_id'),
        Index('ix_esgsi_scope', 'encounter_set_scope_id'),
        Index('ix_esgsi_task', 'task_id'),
        Index('ix_esgsi_grade', 'grade_id'),
        Index('ix_esgsi_scope_disease', 'scope_disease_id'),
    )


class AIInferenceRun(Base):
    __tablename__ = "ai_inference_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("grading_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    ai_model_id: Mapped[int] = mapped_column(ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_model_integrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="internal", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    external_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    prediction_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    remote_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_manifest_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    initialize_response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    execute_response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    task: Mapped["GradingTask"] = relationship("GradingTask", back_populates="inference_runs")
    ai_model: Mapped["AIModel"] = relationship("AIModel", back_populates="inference_runs")
    integration: Mapped["AIModelIntegration | None"] = relationship("AIModelIntegration", back_populates="inference_runs")
    requested_by: Mapped["User | None"] = relationship("User", foreign_keys=[requested_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "source IN ('internal','mobile','backfill')",
            name="ck_ai_inference_run_source_valid",
        ),
        CheckConstraint(
            "status IN ('queued','running','success','failed')",
            name="ck_ai_inference_run_status_valid",
        ),
        Index("ix_ai_inference_runs_task_model_created", "task_id", "ai_model_id", "created_at"),
    )


class Grade(Base):
    __tablename__ = 'grades'

    id: Mapped[int] = mapped_column(primary_key=True)

    task_id: Mapped[int] = mapped_column(ForeignKey('grading_tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    grader_user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # resident | resident2 | arbitrator | ai | review
    role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # Normalized to master labels for the disease
    disease_grading_id: Mapped[int] = mapped_column(ForeignKey('disease_gradings.id'), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_features_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string storing selected feature metadata (id/label/sr_no)
    feature_geometry_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # JSON geometry payload for feature markings
    time_taken: Mapped[float | None] = mapped_column(Float, nullable=True)  # Time taken in seconds
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # When grading started
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    ai_review_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True
    )
    ai_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Denormalized fields for data integrity and historical preservation
    disease_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Copy of disease.name at time of grading
    grade_name: Mapped[str | None] = mapped_column(String(64), nullable=True)     # Copy of disease_grading.impression at time of grading
    grade_description: Mapped[str | None] = mapped_column(Text, nullable=True)    # Copy of disease_grading.guidelines at time of grading
    
    ai_model_id: Mapped[int | None] = mapped_column(ForeignKey('ai_models.id', ondelete='SET NULL'), nullable=True, index=True)
    # Denormalized AI model metadata (if role_slot == 'ai')
    ai_model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    task: Mapped['GradingTask'] = relationship('GradingTask', back_populates='grades')
    grader: Mapped['User'] = relationship('User', foreign_keys=[grader_user_id])
    label: Mapped['DiseaseGrading'] = relationship('DiseaseGrading')
    ai_model: Mapped[Optional["AIModel"]] = relationship("AIModel", back_populates="grades")
    ai_reviewed_by: Mapped['User | None'] = relationship('User', foreign_keys=[ai_reviewed_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "role_slot IN ('resident','resident2','arbitrator','ai','review','regrade_adj')",
            name='ck_grade_role_slot_valid',
        ),
        CheckConstraint(
            "ai_review_status IS NULL OR ai_review_status IN ('ok','minor_miss','major_miss')",
            name='ck_grade_ai_review_status_valid',
        ),
        Index('ix_grade_task_slot', 'task_id', 'role_slot'),
        Index('ix_grade_user_slot', 'grader_user_id', 'role_slot'),
        UniqueConstraint('task_id', 'grader_user_id', 'role_slot', name='uq_grade_task_user_slot'),
    )


class Consensus(Base):
    __tablename__ = 'consensus'

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('grading_tasks.id', ondelete='CASCADE'), nullable=False, unique=True)
    final_disease_grading_id: Mapped[int] = mapped_column(ForeignKey('disease_gradings.id'), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    consensus_scope: Mapped[str] = mapped_column(String(32), nullable=False, default='image', server_default='image', index=True)
    encounter_set_package_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_set_grading_packages.id', ondelete='SET NULL'), nullable=True, index=True)
    encounter_set_scope_id: Mapped[int | None] = mapped_column(ForeignKey('encounter_set_grading_scopes.id', ondelete='SET NULL'), nullable=True, index=True)
    scope_disease_id: Mapped[int | None] = mapped_column(ForeignKey('diseases.id', ondelete='SET NULL'), nullable=True, index=True)
    scope_disease_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    
    # Denormalized fields for data integrity and historical preservation
    final_disease_name: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Copy of disease.name at time of consensus
    final_grade_name: Mapped[str | None] = mapped_column(String(64), nullable=True)     # Copy of disease_grading.impression at time of consensus
    final_grade_description: Mapped[str | None] = mapped_column(Text, nullable=True)    # Copy of disease_grading.guidelines at time of consensus
    
    task: Mapped['GradingTask'] = relationship('GradingTask', back_populates='consensus')
    final_label: Mapped['DiseaseGrading'] = relationship('DiseaseGrading')
    decided_by: Mapped['User | None'] = relationship('User')

    __table_args__ = (
        CheckConstraint("method IN ('match','adjudication','task_review','regrade')", name='ck_consensus_method_valid'),
        CheckConstraint(
            "consensus_scope IN ('image','encounter_set_unified','encounter_set_disease')",
            name='ck_consensus_scope_valid',
        ),
        CheckConstraint(
            "consensus_scope <> 'encounter_set_disease' OR scope_disease_id IS NOT NULL",
            name='ck_consensus_disease_scope_present',
        ),
    )


class RegradeTask(Base):
    __tablename__ = "regrade_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid4()),
    )
    source_task_id: Mapped[int] = mapped_column(
        ForeignKey("grading_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False, index=True)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id"), nullable=False, index=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="regrade_pending", nullable=False, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    source_task: Mapped["GradingTask"] = relationship("GradingTask")
    disease: Mapped["Disease"] = relationship("Disease")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")
    assigned_to: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_to_user_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('regrade_pending','regrade_done')",
            name="ck_regrade_task_status_valid",
        ),
    )


class CuratedDataset(Base):
    """Dataset definition that captures filter criteria and selected tasks."""

    __tablename__ = "curated_datasets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    disease: Mapped["Disease"] = relationship("Disease", foreign_keys=[disease_id], lazy="selectin")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_user_id], lazy="selectin")
    finalized_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[finalized_by_user_id], lazy="selectin")
    items: Mapped[List["CuratedDatasetItem"]] = relationship(
        "CuratedDatasetItem",
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CuratedDatasetItem(Base):
    """Individual task membership within a curated dataset."""

    __tablename__ = "curated_dataset_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("curated_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("grading_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    include_in_export: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    selection_method: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    selected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    dataset: Mapped["CuratedDataset"] = relationship("CuratedDataset", back_populates="items")
    task: Mapped["GradingTask"] = relationship("GradingTask", lazy="selectin")
    selected_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[selected_by_user_id], lazy="selectin")

    __table_args__ = (
        UniqueConstraint("dataset_id", "task_id", name="uq_curated_dataset_items_dataset_task"),
        CheckConstraint("selection_method IN ('auto','manual')", name="ck_curated_dataset_items_method"),
    )


class DatasetExport(Base):
    """Link dataset exports to their job records."""

    __tablename__ = "dataset_exports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("curated_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    dataset: Mapped["CuratedDataset"] = relationship("CuratedDataset", lazy="selectin")
    job: Mapped["Job"] = relationship("Job", lazy="selectin")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_user_id], lazy="selectin")


class DatasetShare(Base):
    """Share token metadata for curated datasets."""

    __tablename__ = "dataset_shares"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("curated_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_for: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_accepted_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    dataset: Mapped["CuratedDataset"] = relationship("CuratedDataset", lazy="selectin")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_user_id], lazy="selectin")

    __table_args__ = (
        Index("ix_dataset_shares_dataset_active", "dataset_id", "is_active"),
    )


class UserDiseaseUnitRole(Base):
    __tablename__ = 'user_disease_unit_role'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id', ondelete='CASCADE'), nullable=False, index=True)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey('lab_units.id', ondelete='CASCADE'), nullable=False, index=True)
    can_grade_resident: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_grade_resident2: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, name="can_grade_resident2")
    can_arbitrate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    user: Mapped['User'] = relationship('User', foreign_keys=[user_id])
    disease: Mapped['Disease'] = relationship('Disease', foreign_keys=[disease_id])
    lab_unit: Mapped['LabUnit'] = relationship('LabUnit', foreign_keys=[lab_unit_id])

    __table_args__ = (
        UniqueConstraint('user_id', 'disease_id', 'lab_unit_id', name='uq_user_disease_unit_role'),
        CheckConstraint('(can_grade_resident = true) OR (can_grade_resident2 = true) OR (can_arbitrate = true)', name='ck_user_dur_has_any_permission'),
        Index('ix_user_dur_unit_disease', 'lab_unit_id', 'disease_id'),
        Index('ix_user_dur_user_active', 'user_id', 'active'),
    )


class TaskTracker(Base):
    """
    A model to track when users start working on grading tasks.
    This allows us to identify and reset tasks that have been 
    started but not completed within the time limit.
    """
    __tablename__ = 'task_tracker'

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('grading_tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # resident | resident2 | arbitrator
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc)


from enum import Enum

class NotificationType(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SYSTEM = "system"


class Notification(Base):
    """
    Model for storing notifications for both system admins and users.
    This model allows sending notifications about various system events,
    including data issues, system errors, and other important messages.
    """
    __tablename__ = 'notifications'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(20), default=NotificationType.INFO.value, nullable=False)
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=True)  # NULL for system-wide notifications
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationship to recipient user
    recipient: Mapped['User'] = relationship('User', foreign_keys=[recipient_user_id], back_populates='notifications')
    sender: Mapped['User'] = relationship('User', foreign_keys=[sender_user_id], back_populates='sent_notifications')
    reads: Mapped[list['NotificationRead']] = relationship('NotificationRead', back_populates='notification', cascade="all, delete-orphan")

    def mark_as_read(self) -> None:
        self.is_read = True
        self.updated_at = utcnow()


class NotificationRead(Base):
    __tablename__ = 'notification_reads'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey('notifications.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    notification: Mapped['Notification'] = relationship('Notification', back_populates='reads')
    user: Mapped['User'] = relationship('User', lazy='joined')

    __table_args__ = (
        UniqueConstraint('notification_id', 'user_id', name='uq_notification_reads_notification_user'),
    )


class AdHocTaskCreation(Base):
    """Auditable record of an Ad-hoc Task creation workflow.
    Stores filters used, selected images, diseases, and a summary.
    Uses JSON text fields for engine portability.
    """
    __tablename__ = 'ad_hoc_task_creations'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    diseases_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of disease_ids
    max_images: Mapped[int] = mapped_column(Integer, nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, nullable=False)   # JSON snapshot of filters
    selected_image_refs_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array with {source, id}
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)        # JSON outcome summary
    randomized: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    creator: Mapped['User'] = relationship('User', foreign_keys=[created_by_id], lazy='joined')
    # Reverse relation from GradingTask via ad_hoc_id
    tasks: Mapped[list['GradingTask']] = relationship(
        'GradingTask', back_populates='ad_hoc', lazy='selectin'
    )


class AppSetting(Base):
    """Key/value application settings store."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), default="string", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class IntraRaterBatch(Base):
    """Batch metadata for intra-rater reliability assessments."""
    __tablename__ = "intra_rater_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False, index=True)
    lab_unit_id: Mapped[int | None] = mapped_column(ForeignKey("lab_units.id"), nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    cooldown_days_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_images_per_grader: Mapped[int] = mapped_column(Integer, nullable=False)
    normal_grade_id: Mapped[int | None] = mapped_column(ForeignKey("disease_gradings.id"), nullable=True, index=True)
    selection_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    disease: Mapped["Disease"] = relationship("Disease")
    lab_unit: Mapped["LabUnit | None"] = relationship("LabUnit")
    created_by: Mapped["User | None"] = relationship("User")
    normal_grade: Mapped["DiseaseGrading | None"] = relationship("DiseaseGrading")
    tasks: Mapped[list["IntraRaterTask"]] = relationship(
        "IntraRaterTask", back_populates="batch", cascade="all, delete-orphan"
    )
    grades: Mapped[list["IntraRaterGrade"]] = relationship(
        "IntraRaterGrade", back_populates="batch", cascade="all, delete-orphan"
    )


class IntraRaterTask(Base):
    """Individual intra-rater reassessment task scoped to a grader."""
    __tablename__ = "intra_rater_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid4()),
    )
    batch_id: Mapped[int] = mapped_column(ForeignKey("intra_rater_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    grader_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False, index=True)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id"), nullable=False, index=True)
    encounter_file_id: Mapped[int | None] = mapped_column(ForeignKey("encounter_files.id"), nullable=True, index=True)
    direct_image_upload_id: Mapped[int | None] = mapped_column(ForeignKey("direct_image_uploads.id"), nullable=True, index=True)
    source_task_id: Mapped[int | None] = mapped_column(ForeignKey("grading_tasks.id"), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    batch: Mapped["IntraRaterBatch"] = relationship("IntraRaterBatch", back_populates="tasks")
    grader: Mapped["User"] = relationship("User")
    disease: Mapped["Disease"] = relationship("Disease")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")
    encounter_file: Mapped["EncounterFile | None"] = relationship("EncounterFile")
    direct_image_upload: Mapped["DirectImageUpload | None"] = relationship("DirectImageUpload")
    source_task: Mapped["GradingTask | None"] = relationship("GradingTask")
    grades: Mapped[list["IntraRaterGrade"]] = relationship(
        "IntraRaterGrade", back_populates="task", cascade="all, delete-orphan"
    )


class IntraRaterGrade(Base):
    """Grader submission for an intra-rater task."""
    __tablename__ = "intra_rater_grades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("intra_rater_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("intra_rater_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    grader_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    disease_grading_id: Mapped[int] = mapped_column(ForeignKey("disease_gradings.id"), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_features_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string storing selected feature metadata (id/label/sr_no)
    feature_geometry_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # JSON geometry payload for feature markings
    time_taken: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    disease_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grade_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["IntraRaterTask"] = relationship("IntraRaterTask", back_populates="grades")
    batch: Mapped["IntraRaterBatch"] = relationship("IntraRaterBatch", back_populates="grades")
    grader: Mapped["User"] = relationship("User")
    disease_grading: Mapped["DiseaseGrading"] = relationship("DiseaseGrading")


class FlaskSession(Base):
    __tablename__ = "flask_sessions"
    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    user: Mapped["User"] = relationship("User", lazy="selectin")


class MobileAuthSession(Base):
    __tablename__ = "mobile_auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    refresh_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_used_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    allowed_lab_unit_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_disease_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    replaced_by_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("mobile_auth_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="mobile_auth_sessions", lazy="selectin")
    replaced_by_session: Mapped["MobileAuthSession | None"] = relationship(
        "MobileAuthSession",
        remote_side=[id],
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_mobile_auth_sessions_user_device"),
        Index("ix_mobile_auth_sessions_user_device_revoked", "user_id", "device_id", "is_revoked"),
    )

# --- Viewer Settings and Presets Models ---

class ViewerSettings(Base):
    """
    Stores user-specific viewer settings that persist across sessions.
    Replaces localStorage-based settings with database persistence.
    """
    __tablename__ = "viewer_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Loupe settings
    loupe_size: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    loupe_zoom: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    loupe_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Image display settings
    zoom: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    pan_x: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pan_y: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Filter settings
    brightness: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    contrast: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    filter: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")
    
    __table_args__ = (
        CheckConstraint("loupe_size >= 50 AND loupe_size <= 1000", name="ck_viewer_settings_loupe_size"),
        CheckConstraint("loupe_zoom >= 0.5 AND loupe_zoom <= 8.0", name="ck_viewer_settings_loupe_zoom"),
        CheckConstraint("zoom >= 10 AND zoom <= 800", name="ck_viewer_settings_zoom"),
        CheckConstraint("pan_x >= -1200 AND pan_x <= 1200", name="ck_viewer_settings_pan_x"),
        CheckConstraint("pan_y >= -1200 AND pan_y <= 1200", name="ck_viewer_settings_pan_y"),
        CheckConstraint("brightness >= 0 AND brightness <= 10.0", name="ck_viewer_settings_brightness"),
        CheckConstraint("contrast >= 0 AND contrast <= 10.0", name="ck_viewer_settings_contrast"),
        CheckConstraint(
            "filter IN ('none','redfree','greenboost','bluemono','gray','contrast','enhance','greenchannel','blueonly','redgreenfree','greenfree')",
            name="ck_viewer_settings_filter",
        ),
    )


class ViewerPresets(Base):
    """
    Stores user-specific viewer presets (up to 5 per user).
    Each preset contains a complete snapshot of viewer settings.
    """
    __tablename__ = "viewer_presets"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    
    # Preset name (optional, for user reference)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # All viewer settings for this preset
    loupe_size: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    loupe_zoom: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    loupe_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    zoom: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    pan_x: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pan_y: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    brightness: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    contrast: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    filter: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", lazy="selectin")
    
    __table_args__ = (
        UniqueConstraint("user_id", "slot_number", name="uq_viewer_presets_user_slot"),
        CheckConstraint("slot_number >= 1 AND slot_number <= 5", name="ck_viewer_presets_slot_number"),
        CheckConstraint("loupe_size >= 50 AND loupe_size <= 1000", name="ck_viewer_presets_loupe_size"),
        CheckConstraint("loupe_zoom >= 0.5 AND loupe_zoom <= 8.0", name="ck_viewer_presets_loupe_zoom"),
        CheckConstraint("zoom >= 10 AND zoom <= 800", name="ck_viewer_presets_zoom"),
        CheckConstraint("pan_x >= -1200 AND pan_x <= 1200", name="ck_viewer_presets_pan_x"),
        CheckConstraint("pan_y >= -1200 AND pan_y <= 1200", name="ck_viewer_presets_pan_y"),
        CheckConstraint("brightness >= 0 AND brightness <= 10.0", name="ck_viewer_presets_brightness"),
        CheckConstraint("contrast >= 0 AND contrast <= 10.0", name="ck_viewer_presets_contrast"),
        CheckConstraint(
            "filter IN ('none','redfree','greenboost','bluemono','gray','contrast','enhance','greenchannel','blueonly','redgreenfree','greenfree')",
            name="ck_viewer_presets_filter",
        ),
    )

 
# --- Engine and Session Creation ---
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

@event.listens_for(engine, "handle_error")
def _log_sqlalchemy_error(exc_context) -> None:  # pragma: no cover - defensive logging
    """Log uncaught SQLAlchemy exceptions with context for troubleshooting."""

    statement = exc_context.statement or "<no statement>"
    params = exc_context.parameters
    if params:
        params_str = str(params)
        if len(params_str) > 512:
            params_str = params_str[:509] + "..."
    else:
        params_str = "<no parameters>"

    logging.getLogger("sqlalchemy.failure").error(
        "SQLAlchemy failure: statement=%s; params=%s; is_disconnect=%s",
        statement,
        params_str,
        exc_context.is_disconnect,
        exc_info=exc_context.original_exception,
    )

Session = sessionmaker(bind=engine)

# === Thumbnail Cleanup Event Handlers ===

@event.listens_for(DirectImageUpload, 'before_delete')
def cleanup_direct_upload_thumbnails(mapper, connection, target):
    """Clean up thumbnails when DirectImageUpload record is deleted."""
    try:
        from utils.thumbnail_cleanup import delete_thumbnails_for_direct_upload
        import logging

        cleanup_logger = logging.getLogger("thumbnail_cleanup")
        results = delete_thumbnails_for_direct_upload(target.id)

        if results['original_deleted']:
            cleanup_logger.info(
                "Cleaned up original thumbnail for DirectImageUpload %s",
                sanitize_log_value(target.id),
            )
        if results['edited_deleted']:
            cleanup_logger.info(
                "Cleaned up edited thumbnail for DirectImageUpload %s",
                sanitize_log_value(target.id),
            )
        if results['errors']:
            for error in results['errors']:
                cleanup_logger.warning(
                    "Thumbnail cleanup error for DirectImageUpload %s: %s",
                    sanitize_log_value(target.id),
                    sanitize_log_value(error),
                )

    except Exception as e:
        import logging
        cleanup_logger = logging.getLogger("thumbnail_cleanup")
        cleanup_logger.error(
            "Failed to clean up thumbnails for DirectImageUpload %s: %s",
            sanitize_log_value(target.id),
            sanitize_log_value(e),
        )


@event.listens_for(EncounterFile, 'before_delete')
def cleanup_encounter_file_thumbnails(mapper, connection, target):
    """Clean up thumbnails when EncounterFile record is deleted."""
    try:
        from utils.thumbnail_cleanup import delete_thumbnails_for_encounter_file
        import logging

        cleanup_logger = logging.getLogger("thumbnail_cleanup")
        results = delete_thumbnails_for_encounter_file(target.id)

        if results['deleted']:
            cleanup_logger.info(
                "Cleaned up thumbnail for EncounterFile %s",
                sanitize_log_value(target.id),
            )
        if results['errors']:
            for error in results['errors']:
                cleanup_logger.warning(
                    "Thumbnail cleanup error for EncounterFile %s: %s",
                    sanitize_log_value(target.id),
                    sanitize_log_value(error),
                )

    except Exception as e:
        import logging
        cleanup_logger = logging.getLogger("thumbnail_cleanup")
        cleanup_logger.error(
            "Failed to clean up thumbnails for EncounterFile %s: %s",
            sanitize_log_value(target.id),
            sanitize_log_value(e),
        )


@event.listens_for(PatientEncounters, 'before_delete')
def cleanup_patient_encounter_thumbnails(mapper, connection, target):
    """Clean up thumbnails for all encounter files when PatientEncounters record is deleted."""
    try:
        from utils.thumbnail_cleanup import delete_thumbnails_for_patient_encounter
        import logging

        cleanup_logger = logging.getLogger("thumbnail_cleanup")
        results = delete_thumbnails_for_patient_encounter(target.id)

        if results['thumbnails_deleted'] > 0:
            cleanup_logger.info(
                "Cleaned up %s thumbnails for PatientEncounter %s",
                sanitize_log_value(results['thumbnails_deleted']),
                sanitize_log_value(target.id),
            )
        if results['errors']:
            for error in results['errors']:
                cleanup_logger.warning(
                    "Thumbnail cleanup error for PatientEncounter %s: %s",
                    sanitize_log_value(target.id),
                    sanitize_log_value(error),
                )

    except Exception as e:
        import logging
        cleanup_logger = logging.getLogger("thumbnail_cleanup")
        cleanup_logger.error(
            "Failed to clean up thumbnails for PatientEncounter %s: %s",
            sanitize_log_value(target.id),
            sanitize_log_value(e),
        )


class EmailSettings(Base):
    """
    Database-backed email configuration settings.
    Allows dynamic management of email configuration through admin interface.
    """
    __tablename__ = "email_settings"

    # Core SMTP configuration
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    smtp_server: Mapped[str] = mapped_column(String(255), nullable=False, default="localhost")
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_password: Mapped[str] = mapped_column(String(255), nullable=False)  # Should be encrypted
    password_salt: Mapped[str] = mapped_column(String(64), nullable=True)  # Unique salt for password encryption
    from_email: Mapped[str] = mapped_column(String(254), nullable=False)

    # Security settings
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # StartTLS
    use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # SSL/TLS
    verify_certificates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Configuration and debugging
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    debug_logging: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Connection settings
    connection_timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=30)  # seconds

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    creator: Mapped["User"] = relationship(foreign_keys=[created_by], post_update=True)
    updater: Mapped["User"] = relationship(foreign_keys=[updated_by], post_update=True)

    # Constraints
    __table_args__ = (
        CheckConstraint("smtp_port > 0 AND smtp_port <= 65535", name="check_smtp_port_range"),
        CheckConstraint("connection_timeout > 0 AND connection_timeout <= 300", name="check_connection_timeout_range"),
        CheckConstraint("NOT (use_tls AND use_ssl)", name="check_mutually_exclusive_tls_ssl"),
        Index("ix_email_settings_active", "is_active"),
        Index("ix_email_settings_updated", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<EmailSettings(id={self.id}, smtp_server={self.smtp_server}, port={self.smtp_port}, active={self.is_active})>"

    def to_dict(self) -> dict:
        """Convert EmailSettings to dictionary, excluding sensitive password."""
        return {
            "id": self.id,
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "smtp_username": self.smtp_username,
            "from_email": self.from_email,
            "use_tls": self.use_tls,
            "use_ssl": self.use_ssl,
            "verify_certificates": self.verify_certificates,
            "is_active": self.is_active,
            "debug_logging": self.debug_logging,
            "connection_timeout": self.connection_timeout,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }

    @classmethod
    def get_active_settings(cls, db_session) -> Optional["EmailSettings"]:
        """Get the currently active email settings."""
        return db_session.query(cls).filter(cls.is_active == True).first()


    def _get_password_for_use(self) -> str:
        """
        Get the decrypted password for use in connections.

        Returns:
            str: Decrypted password
        """
        from utils.encryption import decrypt_password_with_salt, decrypt_password
        import logging

        if not self.smtp_password:
            return ""

        # If we have a salt, use salted decryption
        if self.password_salt:
            try:
                return decrypt_password_with_salt(self.smtp_password, self.password_salt)
            except Exception as e:
                # Fall back to default decryption for backward compatibility
                logging.warning(
                    "Failed to decrypt password with salt for email settings %s, falling back to default salt: %s",
                    sanitize_log_value(self.id),
                    sanitize_log_value(e),
                )
                pass

        # Try default decryption (for backward compatibility with existing passwords)
        try:
            return decrypt_password(self.smtp_password)
        except Exception as e:
            # If all decryption fails, assume it's plaintext (very old passwords)
            logging.warning(
                "Failed to decrypt password for email settings %s, assuming plaintext: %s",
                sanitize_log_value(self.id),
                sanitize_log_value(e),
            )
            return self.smtp_password

    def set_password(self, plain_password: str) -> None:
        """
        Set and encrypt the password using a unique salt.

        Args:
            plain_password (str): Plain text password to encrypt and store
        """
        from utils.encryption import encrypt_password_with_salt, generate_salt

        # Generate a unique salt for this email setting
        self.password_salt = generate_salt()

        # Encrypt the password using the unique salt
        self.smtp_password = encrypt_password_with_salt(plain_password, self.password_salt)

    def get_password_for_display(self) -> str:
        """
        Get a masked version of the password for display purposes.

        Returns:
            str: Masked password (e.g., "••••••••••••")
        """
        if not self.smtp_password:
            return ""

        # Return masked version regardless of whether encrypted or not
        return "•" * min(len(self.smtp_password), 12)


class SensitiveOperationAudit(Base):
    """
    Audit trail for sensitive data operations.
    
    This model tracks all sensitive operations such as database exports,
    data downloads, and bulk data access to maintain a security audit trail.
    
    Reference: docs/PII_Exposure_Control_Policy.md Section 6A.3
    Bead: 5N-1 (fundus_img_xtract-1yu)
    """
    __tablename__ = "sensitive_operations_audit"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # User who performed the operation
    user_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # Allow null if user is deleted
        index=True
    )
    
    # Type of operation performed
    operation_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )
    # Examples: 'database_dump', 'database_excel_export', 'discrepancy_export', 
    #           'dataset_export', 'user_pii_access', 'bulk_data_download'
    
    # Status of the operation
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    # Values: 'initiated', 'reauth_success', 'reauth_failed', 'completed', 'failed', 'cancelled'
    
    # Client information
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Request details (filters, table names, parameters used)
    request_details: Mapped[dict | None] = mapped_column(
        Text,  # Store as JSON string
        nullable=True
    )
    
    # Result details (row_count, file_hash, file_size)
    result_details: Mapped[dict | None] = mapped_column(
        Text,  # Store as JSON string
        nullable=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True
    )
    
    # Relationship to user
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    
    def __repr__(self) -> str:
        return (
            f"<SensitiveOperationAudit(id={self.id}, user_id={self.user_id}, "
            f"operation='{self.operation_type}', status='{self.status}')>"
        )
    
    def set_request_details(self, details: dict) -> None:
        """Serialize request details to JSON string."""
        import json
        self.request_details = json.dumps(details) if details else None
    
    def get_request_details(self) -> dict | None:
        """Deserialize request details from JSON string."""
        import json
        if not self.request_details:
            return None
        try:
            return json.loads(self.request_details)
        except (json.JSONDecodeError, TypeError):
            return None
    
    def set_result_details(self, details: dict) -> None:
        """Serialize result details to JSON string."""
        import json
        self.result_details = json.dumps(details) if details else None
    
    def get_result_details(self) -> dict | None:
        """Deserialize result details from JSON string."""
        import json
        if not self.result_details:
            return None
        try:
            return json.loads(self.result_details)
        except (json.JSONDecodeError, TypeError):
            return None


class CVEScanResult(Base):
    """
    Stores results of pip-audit vulnerability scans.
    
    Scheduled scans run daily via Celery and results are stored here.
    On-demand scans can also be triggered by admins.
    """
    __tablename__ = "cve_scan_results"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    scan_type: Mapped[str] = mapped_column(
        String(20),
        default="scheduled",
        nullable=False,
        index=True
    )  # "scheduled" or "on_demand"
    
    status: Mapped[str] = mapped_column(
        String(20),
        default="completed",
        nullable=False
    )  # "completed", "failed", "running"
    
    # Total packages scanned (for context)
    packages_scanned_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Vulnerability counts
    total_count: Mapped[int] = mapped_column(default=0, nullable=False)
    critical_count: Mapped[int] = mapped_column(default=0, nullable=False)
    high_count: Mapped[int] = mapped_column(default=0, nullable=False)
    medium_count: Mapped[int] = mapped_column(default=0, nullable=False)
    low_count: Mapped[int] = mapped_column(default=0, nullable=False)
    
    # Full scan results as JSON
    vulnerabilities_json: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)

    # All packages scanned (for reference)
    packages_scanned_json: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)
    
    # Raw pip-audit output for debugging
    raw_output: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)
    
    # Error message if scan failed
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Who triggered the scan (None for scheduled)
    triggered_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )
    
    # Scan duration in seconds
    duration_seconds: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    def get_vulnerabilities(self) -> list:
        """Deserialize vulnerabilities JSON to list."""
        import json
        if not self.vulnerabilities_json:
            return []
        try:
            return json.loads(self.vulnerabilities_json)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_vulnerabilities(self, vulnerabilities: list) -> None:
        """Serialize vulnerabilities list to JSON."""
        import json
        self.vulnerabilities_json = json.dumps(vulnerabilities) if vulnerabilities else None

    def get_packages_scanned(self) -> list:
        """Deserialize packages_scanned JSON to list."""
        import json
        if not self.packages_scanned_json:
            return []
        try:
            return json.loads(self.packages_scanned_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_packages_scanned(self, packages: list) -> None:
        """Serialize packages list to JSON."""
        import json
        self.packages_scanned_json = json.dumps(packages) if packages else None
    
    def has_critical_or_high(self) -> bool:
        """Check if scan found any critical or high vulnerabilities."""
        return self.critical_count > 0 or self.high_count > 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
            "scan_type": self.scan_type,
            "status": self.status,
            "packages_scanned": self.packages_scanned_count,
            "total_count": self.total_count,
            "by_severity": {
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
            },
            "has_critical_or_high": self.has_critical_or_high(),
            "vulnerabilities": self.get_vulnerabilities(),
            "error": self.error_message,
            "triggered_by_user_id": self.triggered_by_user_id,
            "duration_seconds": self.duration_seconds,
        }


class PackageUpdateScan(Base):
    """
    Stores results of Python package update scans from PyPI.

    Checks ALL installed packages for available updates (not just vulnerable ones).
    Scheduled scans run daily via Celery Beat at 3 AM UTC.
    On-demand scans can be triggered by admins.
    Results older than 200 days are automatically cleaned up.
    """
    __tablename__ = "package_update_scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    scan_type: Mapped[str] = mapped_column(
        String(20),
        default="scheduled",
        nullable=False,
        index=True
    )  # "scheduled" or "on_demand"

    status: Mapped[str] = mapped_column(
        String(20),
        default="completed",
        nullable=False
    )  # "completed", "failed", "running"

    # Package counts
    packages_scanned_count: Mapped[int] = mapped_column(default=0, nullable=False)
    updates_available_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Full scan results as JSON (all packages with version info)
    packages_json: Mapped[Optional[Text]] = mapped_column(Text, nullable=True)

    # Error message if scan failed
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Who triggered the scan (None for scheduled)
    triggered_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )

    # Scan duration in seconds
    duration_seconds: Mapped[Optional[int]] = mapped_column(nullable=True)

    def get_packages(self) -> list:
        """Deserialize packages JSON to list."""
        import json
        if not self.packages_json:
            return []
        try:
            return json.loads(self.packages_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_packages(self, packages: list) -> None:
        """Serialize packages list to JSON."""
        import json
        self.packages_json = json.dumps(packages) if packages else None

    def has_updates(self) -> bool:
        """Check if scan found any available updates."""
        return self.updates_available_count > 0

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
            "scan_type": self.scan_type,
            "status": self.status,
            "packages_scanned": self.packages_scanned_count,
            "updates_available": self.updates_available_count,
            "has_updates": self.has_updates(),
            "packages": self.get_packages(),
            "error": self.error_message,
            "triggered_by_user_id": self.triggered_by_user_id,
            "duration_seconds": self.duration_seconds,
        }


# Import feature-specific model modules so their tables are registered on
# Base.metadata while keeping this root model file from growing indefinitely.
from upload_profiles.models import (  # noqa: E402,F401
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileArea,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeGradingPackage,
    UploadProfileEncounterSetTypeImageGradingScheme,
    UploadProfileEncounterSetTypePackageEncounterScheme,
    UploadProfileEncounterSetTypePackageImageScheme,
    UploadProfileKind,
    PatientEncounterTargetDisease,
)
from encounter_set_types.models import EncounterSetType  # noqa: E402,F401
from iitk_api_integration.models import IITKApiProjectConfig, IITKApiSessionLink  # noqa: E402,F401
from upload_metadata.models import UploadMetadataFieldDefinition  # noqa: E402,F401
from encounter_sets.models import EncounterSetAttachment  # noqa: E402,F401
from remidio_api_integration.models import (  # noqa: E402,F401
    RemidioApiExamEncounter,
    RemidioApiRoutingProfile,
    ProjectUploadProfileRemidioApiBinding,
    RemidioApiSourceRule,
)
from remote_inference.models import (  # noqa: E402,F401
    DiseaseReportLinkage,
    EncounterAIImageResult,
    EncounterAIInferenceRun,
    EncounterAIOutputTarget,
    EncounterAITargetResult,
    ProjectAutomatedRemoteInferenceRule,
    ProjectEncounterAIWorkflow,
    ProjectManualRemoteInferenceWorkflow,
)
from grading_allocation.models import (  # noqa: E402,F401
    ProjectGraderAllocation,
    ProjectGradingAllocationPolicy,
)
from project_annotations.models import (  # noqa: E402,F401
    ProjectAnnotationClass,
    ProjectAnnotationPolicy,
    ProjectAnnotationPolicyRevision,
    ProjectAnnotationTool,
)
from grading.workbench.models import (  # noqa: E402,F401
    AnnotationInstance,
    AnnotationMaskTile,
    AnnotationSet,
    GradingSubmissionEvent,
    GradingSubmissionEventItem,
    GradingWorkbenchSession,
    GradingWorkbenchSessionTarget,
)
from data_authorization.models import ProjectRoleGrant  # noqa: E402,F401
from project_configuration.models import ProjectLabUnit  # noqa: E402,F401
