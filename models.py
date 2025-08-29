import os
from pathlib import Path
from sqlalchemy import Date, create_engine, Integer, String, ForeignKey, Boolean, DateTime, Text, Index, UniqueConstraint
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase, Mapped, mapped_column
from datetime import date, datetime, timezone
from typing import Optional
from dotenv import load_dotenv   
from uuid import uuid4




# --- Load environment ---
load_dotenv()

# --- Database and File Path Configuration ---
# Central place for all path and DB configurations
BASE_DIR = Path(__file__).resolve().parent


# Database URL (already wired)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'zip_processing.db'}")

# --- File processing directories from .env ---
UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "files/uploaded")
IMAGE_DIR = BASE_DIR / os.getenv("IMAGE_DIR", "files/images")
PDF_DIR = BASE_DIR / os.getenv("PDF_DIR", "files/pdfs")
PROCESSED_DIR = BASE_DIR / os.getenv("PROCESSED_DIR", "files/processed")
PROCESSING_ERROR_DIR = BASE_DIR / os.getenv("PROCESSING_ERROR_DIR", "files/processing_error")

def utcnow():
    return datetime.now(timezone.utc)


# --- SQLAlchemy Setup ---
# Base class for our declarative models using modern syntax
class Base(DeclarativeBase):
    pass

class ZipFile(Base):
    """SQLAlchemy model for the zip_files table."""
    __tablename__ = 'zip_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    zip_filename: Mapped[str] = mapped_column(unique=True)
    md5_hash: Mapped[str] = mapped_column(unique=True)
    
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="zip_file", uselist=False, cascade="all, delete-orphan")

class PatientEncounters(Base):
    """SQLAlchemy model for the patient_encounters table."""
    __tablename__ = 'patient_encounters'
    id: Mapped[int] = mapped_column(primary_key=True)
    zip_file_id: Mapped[int] = mapped_column(ForeignKey('zip_files.id'), unique=True)
    name: Mapped[str]
    patient_id: Mapped[str]
    capture_date: Mapped[str]
    # New: proper Date column for reliable queries (nullable until backfilled)
    capture_date_dt: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    
    zip_file: Mapped["ZipFile"] = relationship(back_populates="patient_encounter")
    encounter_files: Mapped[list["EncounterFile"]] = relationship(
        back_populates="patient_encounter", cascade="all, delete-orphan"
    )
    dr_reports: Mapped[list["DiabeticRetinopathyReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")
    glaucoma_reports: Mapped[list["GlaucomaReport"]] = relationship(back_populates="patient_encounter", cascade="all, delete-orphan")

class EncounterFile(Base):
    """SQLAlchemy model for the encounter_files table."""
    __tablename__ = 'encounter_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    filename: Mapped[str]
    file_type: Mapped[str]
    ocr_processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    # New: stable unique identifier for each extracted file
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_files")

class DiabeticRetinopathyReport(Base):
    """Stores extracted data from DR reports."""
    __tablename__ = 'diabetic_retinopathy_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    # Stable identifier for public/secure links to split DR PDFs
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    result: Mapped[str]
    # New field to store additional qualitative results from OCR
    qualitative_result: Mapped[str | None] = mapped_column(nullable=True)
    # New field to store the name of the split DR PDF file
    report_file_name: Mapped[str | None] = mapped_column(nullable=True)
    
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="dr_reports")

class GlaucomaReport(Base):
    """Stores extracted data from Glaucoma reports."""
    __tablename__ = 'glaucoma_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    # Stable identifier for public/secure links to split Glaucoma PDFs
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid4()))
    vcdr_right: Mapped[str | None]
    vcdr_left: Mapped[str | None]
    result: Mapped[str]
    # New field to store additional qualitative results from OCR
    qualitative_result: Mapped[str | None] = mapped_column(nullable=True)
    # New field to store the name of the split Glaucoma PDF file
    report_file_name: Mapped[str | None] = mapped_column(nullable=True)
    
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="glaucoma_reports")



# --- Jobs: persist async processing state ---



class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # optional external/public token if you prefer non-sequential ids
    token: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="queued")   # queued|processing|done|error
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejected_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # one-line summary
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items: Mapped[list["JobItem"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

class JobItem(Base):
    __tablename__ = "job_items"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    filename: Mapped[str]
    state: Mapped[str] = mapped_column(default="queued")  # queued|processing|ok|error
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    job: Mapped["Job"] = relationship(back_populates="items")





# --- existing User model: ADD the relationship + helper methods ---
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Profile fields ---
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    year_of_joining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_date_of_service: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # NEW: roles many-to-many
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        lazy="selectin",
    )


    # Flask-Login helpers (keep as before) ...
    @property
    def is_authenticated(self) -> bool:  # noqa
        return True
    @property
    def is_anonymous(self) -> bool:  # noqa
        return False
    def get_id(self) -> str:  # noqa
        return str(self.id)

    # NEW: convenience checks
    def has_role(self, *names: str) -> bool:
        user_roles = {r.name.lower() for r in (self.roles or [])}
        return any(n.lower() in user_roles for n in names)

    def has_all_roles(self, *names: str) -> bool:
        user_roles = {r.name.lower() for r in (self.roles or [])}
        return all(n.lower() in user_roles for n in names)

# --- NEW: Role model ---
class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    users: Mapped[list["User"]] = relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
    )

# --- NEW: association table ---
class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        Index("ix_user_roles_user", "user_id"),
        Index("ix_user_roles_role", "role_id"),
    )


class LoginAttempt(Base):
    """
    Record every login attempt (success or failure) with typed username and client IP.
    We aggregate by rolling windows to decide throttling/lockouts.
    """
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username_input: Mapped[str] = mapped_column(String(150), nullable=False)  # exactly what user typed
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)

    __table_args__ = (
        Index("ix_login_attempts_username_created", "username_input", "created_at"),
        Index("ix_login_attempts_ip_created", "ip_address", "created_at"),
    )

class IpLock(Base):
    """
    Locks a client IP for a period.
    """
    __tablename__ = "ip_locks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip_address: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("ip_address", name="uq_iplock_ip"),)

 

# --- Engine and Session Creation ---
# A single engine and session factory can be imported by other scripts
# If you’ll process jobs in background threads, update your engine to allow cross-thread use:
# ✅ Engine with thread safety for SQLite
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Session = sessionmaker(bind=engine)

