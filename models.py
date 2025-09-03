import os
from pathlib import Path
from sqlalchemy import (
    CheckConstraint, Date, create_engine, Integer, String, ForeignKey, Boolean, DateTime, Text,
    Index, UniqueConstraint, Table, Column
)
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase, Mapped, mapped_column
from datetime import date, datetime, timezone
from typing import Optional, List
from dotenv import load_dotenv
from uuid import uuid4

# --- Load environment ---
load_dotenv()

# --- Database and File Path Configuration ---
BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'zip_processing.db'}")
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "files/uploaded")
IMAGE_DIR = BASE_DIR / os.getenv("IMAGE_DIR", "files/images")
PDF_DIR = BASE_DIR / os.getenv("PDF_DIR", "files/pdfs")
PROCESSED_DIR = BASE_DIR / os.getenv("PROCESSED_DIR", "files/processed")
PROCESSING_ERROR_DIR = BASE_DIR / os.getenv("PROCESSING_ERROR_DIR", "files/processing_error")
DIRECT_UPLOAD_DIR = BASE_DIR / os.getenv("DIRECT_UPLOAD_DIR", "files/direct_uploads")



def utcnow():
    return datetime.now(timezone.utc)

# --- SQLAlchemy Setup ---
class Base(DeclarativeBase):
    pass

# --- Association Table for User <-> LabUnit ---
user_lab_units = Table(
    'user_lab_units', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True),
    Column('lab_unit_id', Integer, ForeignKey('lab_units.id', ondelete="CASCADE"), primary_key=True)
)

class ZipFile(Base):
    __tablename__ = 'zip_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    zip_filename: Mapped[str] = mapped_column(unique=True)
    md5_hash: Mapped[str] = mapped_column(unique=True)
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
    zip_file: Mapped["ZipFile"] = relationship(back_populates="patient_encounter")
    encounter_files: Mapped[List["EncounterFile"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    dr_reports: Mapped[List["DiabeticRetinopathyReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    glaucoma_reports: Mapped[List["GlaucomaReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")

class EncounterFile(Base):
    __tablename__ = 'encounter_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    filename: Mapped[str]
    file_type: Mapped[str]
    ocr_processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    eye_side: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_files")
    gradings: Mapped[List["ImageGrading"]] = relationship(back_populates="image", cascade="all, delete-orphan")

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
    patient_encounter: Mapped["PatientEncounters"] = relationship("PatientEncounters")
    glaucoma_report: Mapped["GlaucomaReport"] = relationship("GlaucomaReport")

class ImageGrading(Base):
    __tablename__ = 'image_gradings'
    id: Mapped[int] = mapped_column(primary_key=True)
    encounter_file_id: Mapped[int] = mapped_column(ForeignKey('encounter_files.id'), index=True)
    grader_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    grader_username: Mapped[str | None] = mapped_column(String(150), nullable=True)
    grader_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    graded_for: Mapped[str] = mapped_column(String(32), index=True)
    impression: Mapped[str] = mapped_column(String(32))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    image: Mapped["EncounterFile"] = relationship(back_populates="gradings")
    grader: Mapped["User"] = relationship("User", foreign_keys=[grader_user_id])
    __table_args__ = (Index('ix_image_gradings_image_user_role_for', 'encounter_file_id', 'grader_user_id', 'grader_role', 'graded_for'),)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="queued")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejected_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    uploader_username: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    uploader_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    items: Mapped[List["JobItem"]] = relationship(back_populates="job", cascade="all, delete-orphan")

class JobItem(Base):
    __tablename__ = "job_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    filename: Mapped[str]
    state: Mapped[str] = mapped_column(default="queued")
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    uploader_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    uploader_username: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    uploader_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job: Mapped["Job"] = relationship(back_populates="items")

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
    roles: Mapped[List["Role"]] = relationship("Role", secondary="user_roles", back_populates="users", lazy="selectin")
    lab_units: Mapped[List["LabUnit"]] = relationship("LabUnit", secondary=user_lab_units, back_populates="users")

    @property
    def is_authenticated(self) -> bool: return True
    @property
    def is_anonymous(self) -> bool: return False
    def get_id(self) -> str: return str(self.id)
    def has_role(self, *names: str) -> bool:
        user_roles = {r.name.lower() for r in (self.roles or [])}
        return any(n.lower() in user_roles for n in names)
    def has_all_roles(self, *names: str) -> bool:
        user_roles = {r.name.lower() for r in (self.roles or [])}
        return all(n.lower() in user_roles for n in names)

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

# --- New Lookup Tables (Masters) ---
class Hospital(Base):
    __tablename__ = 'hospitals'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    lab_units: Mapped[List["LabUnit"]] = relationship(
        back_populates="hospital", lazy="selectin", cascade="all, delete-orphan"
    )


class LabUnit(Base):
    __tablename__ = 'lab_units'
    __table_args__ = (
        UniqueConstraint("name", "hospital_id", name="uq_labunit_name_per_hospital"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hospital_id: Mapped[int] = mapped_column(ForeignKey('hospitals.id'), nullable=False)

    hospital: Mapped["Hospital"] = relationship(
        back_populates="lab_units", lazy="selectin"
    )
    users: Mapped[List["User"]] = relationship(
        "User", secondary=user_lab_units, back_populates="lab_units", lazy="selectin"
    )



class Camera(Base):
    __tablename__ = 'cameras'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

class Disease(Base):
    __tablename__ = 'diseases'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

class Area(Base):
    __tablename__ = 'areas'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)



# --- Direct Image Upload Table ---
class DirectImageUpload(Base):
    __tablename__ = "direct_image_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)

    # SQLite-friendly UUID-as-string
    uuid: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )

    # Basenames only
    filename: Mapped[str] = mapped_column(String(255), nullable=False)          # original file name (basename)
    edited_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # edited basename (under <folder_rel>/edited/)

    # POSIX-style relative directory from BASE_DIR (e.g., "files/direct_uploads/2025_09_01_user7")
    folder_rel: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    file_hash: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    hospital_id: Mapped[int] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    lab_unit_id: Mapped[int] = mapped_column(ForeignKey("lab_units.id"), nullable=False)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), nullable=False)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), nullable=False)

    is_mydriatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    # Relationships
    uploader: Mapped["User"] = relationship()
    hospital: Mapped["Hospital"] = relationship()
    lab_unit: Mapped["LabUnit"] = relationship()
    camera: Mapped["Camera"] = relationship()
    disease: Mapped["Disease"] = relationship()
    area: Mapped["Area"] = relationship()

    __table_args__ = (
        # Basename only (no slashes)
        CheckConstraint("instr(filename, '/') = 0", name="ck_diu_filename_no_slash"),
        CheckConstraint(
            "edited_filename IS NULL OR instr(edited_filename, '/') = 0",
            name="ck_diu_edited_filename_no_slash",
        ),
        # folder_rel should be a relative POSIX path (no leading '/', no backslashes)
        CheckConstraint("substr(folder_rel, 1, 1) <> '/'", name="ck_diu_folder_not_absolute"),
        CheckConstraint("instr(folder_rel, '\\\\') = 0", name="ck_diu_folder_no_backslash"),
        # Helpful composite indexes
        Index("ix_diu_uploader_created", "uploader_id", "created_at"),
        Index("ix_diu_folder_created", "folder_rel", "created_at"),
    )

    # Convenience (display/debug only; do NOT serve from here)
    @property
    def rel_dir(self) -> str:
        return self.folder_rel

    @property
    def has_edited(self) -> bool:
        return bool(self.edited_filename)
    
    verifications: Mapped[List["DirectImageVerify"]] = relationship(
        back_populates="image_upload", cascade="all, delete-orphan"
    )


class DirectImageVerify(Base):
    __tablename__ = "direct_image_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)

    image_upload_id: Mapped[int] = mapped_column(
        ForeignKey("direct_image_uploads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verified_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    image_upload: Mapped["DirectImageUpload"] = relationship(back_populates="verifications")
    verified_by: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("image_upload_id", name="uq_direct_image_verify_upload_id"),
        CheckConstraint(
            "verified_status IN ('verified', 'unverified', 'pending')",
            name="ck_di_verify_status",
        ),
    )


# --- Engine and Session Creation ---
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Session = sessionmaker(bind=engine)
