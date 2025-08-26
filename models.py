import os
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, Float, DateTime, Text
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase, Mapped, mapped_column
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv   # ✅ add this


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
    
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="encounter_files")

class DiabeticRetinopathyReport(Base):
    """Stores extracted data from DR reports."""
    __tablename__ = 'diabetic_retinopathy_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
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



# --- Engine and Session Creation ---
# A single engine and session factory can be imported by other scripts
# If you’ll process jobs in background threads, update your engine to allow cross-thread use:
# ✅ Engine with thread safety for SQLite
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Session = sessionmaker(bind=engine)

def create_db_and_tables():
    """A function to initialize the database and create tables."""
    print("Creating database and tables if they don't exist...")
    Base.metadata.create_all(engine)
    print("Database is ready.")

if __name__ == '__main__':
    # This allows you to set up the database by running `python models.py`
    create_db_and_tables()
