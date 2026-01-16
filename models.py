import logging
import os
from pathlib import Path
from urllib.parse import quote, urlparse
from sqlalchemy import (CheckConstraint, Date, create_engine, Integer, String, ForeignKey, Boolean, DateTime, Text, Index, UniqueConstraint, Table, Column, Float, event)
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase, Mapped, mapped_column
from datetime import date, datetime, timezone
from typing import Optional, List
from uuid import uuid4

from utils.env_loader import load_environment
from auth.utils import utcnow
from utils.log_sanitize import sanitize_log_value

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

class Base(DeclarativeBase):
    pass

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

    @property
    def is_authenticated(self) -> bool: return True
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

class Disease(Base):
    __tablename__ = 'diseases'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    disease_gradings: Mapped[List["DiseaseGrading"]] = relationship("DiseaseGrading", back_populates="disease")

class Area(Base):
    __tablename__ = 'areas'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

class DiseaseGrading(Base):
    __tablename__ = 'disease_gradings'
    id: Mapped[int] = mapped_column(primary_key=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id'), nullable=False)
    impression: Mapped[str] = mapped_column(String(64), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    guidelines: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disease: Mapped["Disease"] = relationship("Disease", back_populates="disease_gradings")
    features: Mapped[List["GradingsFeatures"]] = relationship("GradingsFeatures", back_populates="disease_grading", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint('disease_id', 'impression', name='uq_disease_grading_disease_impression'),
        Index('ix_disease_gradings_disease_order', 'disease_id', 'display_order'),
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
    zip_file_id: Mapped[int] = mapped_column(ForeignKey('zip_files.id'), unique=True)
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

    zip_file: Mapped["ZipFile"] = relationship(back_populates="patient_encounter")
    encounter_files: Mapped[List["EncounterFile"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    encounter_file_pdfs: Mapped[List["EncounterFilePDF"]] = relationship(cascade="all, delete-orphan")
    dr_reports: Mapped[List["DiabeticRetinopathyReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    glaucoma_reports: Mapped[List["GlaucomaReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    glaucoma_results_cleaned: Mapped[List["GlaucomaResultsCleaned"]] = relationship()
    lab_unit: Mapped["LabUnit"] = relationship()

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
    thumbnail_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # thumbnail basename (thm_uuid.ext)
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_files")
    lab_unit: Mapped["LabUnit"] = relationship()
    # Note: ImageGrading relationship removed - now using Grade model through GradingTask
    # Add a check constraint to ensure only image files are stored in this table
    __table_args__ = (
        CheckConstraint("file_type != 'pdf'", name="ck_encounter_file_not_pdf"),
        CheckConstraint("thumbnail_filename IS NULL OR position('/' in thumbnail_filename) = 0", name="ck_ef_thumbnail_filename_no_slash"),
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
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_file_pdfs")
    lab_unit: Mapped["LabUnit"] = relationship()
    
    # Add a check constraint to ensure only PDF files are stored in this table
    __table_args__ = (
        CheckConstraint("file_type = 'pdf'", name="ck_encounter_file_pdf_only"),
        Index('ix_encounter_file_pdfs_patient_encounter_id', 'patient_encounter_id')
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    uploader_username: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    uploader_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lab_unit_id: Mapped[int | None] = mapped_column(ForeignKey("lab_units.id"), nullable=True, index=True)
    items: Mapped[List["JobItem"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    lab_unit: Mapped["LabUnit"] = relationship("LabUnit")

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
    job: Mapped["Job"] = relationship(back_populates="items")





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
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), nullable=False)
    is_mydriatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pregraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    thumbnail_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # thumbnail basename (thm_uuid.ext)
    edited_thumbnail_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # edited thumbnail basename (thm_uuid.ext)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    # Relationships
    uploader: Mapped["User"] = relationship(foreign_keys=[uploader_id])
    hospital: Mapped["Hospital"] = relationship()
    lab_unit: Mapped["LabUnit"] = relationship()
    camera: Mapped["Camera"] = relationship()
    disease: Mapped["Disease"] = relationship()
    area: Mapped["Area"] = relationship()

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
        CheckConstraint("verified_status IN ('verified', 'unverified', 'pending')", name="ck_di_verify_status",),
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

    disease_id: Mapped[int] = mapped_column(ForeignKey('diseases.id'), nullable=False, index=True)
    # lab_unit_id is used strictly for grading assignment and queue scoping.
    # It does not redefine image identity; uniqueness is enforced across labs.
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey('lab_units.id'), nullable=False, index=True)

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
    grades: Mapped[list['Grade']] = relationship('Grade', back_populates='task', cascade="all, delete-orphan")
    consensus: Mapped['Consensus | None'] = relationship(
        'Consensus', back_populates='task', uselist=False, cascade="all, delete-orphan", single_parent=True
    )

    # Relationship added after class AdHocTaskCreation definition
    ad_hoc: Mapped['AdHocTaskCreation | None'] = relationship(
        'AdHocTaskCreation', back_populates='tasks', lazy='selectin'
    )

    __table_args__ = (
        # Ensure one and only one image reference is set
        CheckConstraint(
            "(encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)",
            name='ck_grading_task_either_encounter_or_direct'
        ),
        # Unique per image×disease across all lab units (enforces single task/gold standard globally).
        # SQLite treats NULLs as distinct; works with the one-of-two FK check above.
        UniqueConstraint('encounter_file_id', 'disease_id', name='uq_task_encounter_disease'),
        UniqueConstraint('direct_image_upload_id', 'disease_id', name='uq_task_direct_disease'),
        CheckConstraint(
            "state IN ('pending','resident_done','resident2_done','arbitration','final')",
            name='ck_task_state_valid'
        ),
        Index('ix_task_disease_lab_state', 'disease_id', 'lab_unit_id', 'state'),
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
        CheckConstraint("role_slot IN ('resident','resident2','arbitrator','ai','review')", name='ck_grade_role_slot_valid'),
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
        CheckConstraint("method IN ('match','adjudication','task_review')", name='ck_consensus_method_valid'),
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    disease: Mapped["Disease"] = relationship("Disease", foreign_keys=[disease_id], lazy="selectin")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_user_id], lazy="selectin")
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
        CheckConstraint("loupe_size >= 100 AND loupe_size <= 500", name="ck_viewer_settings_loupe_size"),
        CheckConstraint("loupe_zoom >= 1.0 AND loupe_zoom <= 4.0", name="ck_viewer_settings_loupe_zoom"),
        CheckConstraint("zoom >= 40 AND zoom <= 500", name="ck_viewer_settings_zoom"),
        CheckConstraint("pan_x >= -600 AND pan_x <= 600", name="ck_viewer_settings_pan_x"),
        CheckConstraint("pan_y >= -600 AND pan_y <= 600", name="ck_viewer_settings_pan_y"),
        CheckConstraint("brightness >= 0.5 AND brightness <= 1.5", name="ck_viewer_settings_brightness"),
        CheckConstraint("contrast >= 0.5 AND contrast <= 1.5", name="ck_viewer_settings_contrast"),
        CheckConstraint("filter IN ('none','redfree','greenboost','bluemono','gray','contrast')", name="ck_viewer_settings_filter"),
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
        CheckConstraint("loupe_size >= 100 AND loupe_size <= 500", name="ck_viewer_presets_loupe_size"),
        CheckConstraint("loupe_zoom >= 1.0 AND loupe_zoom <= 4.0", name="ck_viewer_presets_loupe_zoom"),
        CheckConstraint("zoom >= 40 AND zoom <= 500", name="ck_viewer_presets_zoom"),
        CheckConstraint("pan_x >= -600 AND pan_x <= 600", name="ck_viewer_presets_pan_x"),
        CheckConstraint("pan_y >= -600 AND pan_y <= 600", name="ck_viewer_presets_pan_y"),
        CheckConstraint("brightness >= 0.5 AND brightness <= 1.5", name="ck_viewer_presets_brightness"),
        CheckConstraint("contrast >= 0.5 AND contrast <= 1.5", name="ck_viewer_presets_contrast"),
        CheckConstraint("filter IN ('none','redfree','greenboost','bluemono','gray','contrast')", name="ck_viewer_presets_filter"),
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
