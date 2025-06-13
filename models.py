import os
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, Float
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase, Mapped, mapped_column

# --- Database and File Path Configuration ---
# Central place for all path and DB configurations
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "zip_processing.db"
DATABASE_URL = f"sqlite:///{DB_FILE}"

# File processing directories
UPLOAD_DIR = BASE_DIR / "files/uploaded"
IMAGE_DIR = BASE_DIR / "files/images"
PDF_DIR = BASE_DIR / "files/pdfs"
PROCESSED_DIR = BASE_DIR / "files/processed"
PROCESSING_ERROR_DIR = BASE_DIR / "files/processing_error"


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
    
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="dr_reports")

class GlaucomaReport(Base):
    """Stores extracted data from Glaucoma reports."""
    __tablename__ = 'glaucoma_reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    patient_encounter_id: Mapped[int] = mapped_column(ForeignKey('patient_encounters.id'))
    vcdr_right: Mapped[float | None]
    vcdr_left: Mapped[float | None]
    result: Mapped[str]
    
    patient_encounter: Mapped["PatientEncounters"] = relationship(back_populates="glaucoma_reports")

# --- Engine and Session Creation ---
# A single engine and session factory can be imported by other scripts
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
