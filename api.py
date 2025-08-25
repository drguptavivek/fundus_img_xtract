# api.py
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import selectinload
from typing import List, Optional
from fastapi.responses import FileResponse
from pathlib import Path

from pydantic import BaseModel, Field

# Import database engine and session factory from your models.py
from models import engine, Session, PatientEncounters, DiabeticRetinopathyReport, GlaucomaReport, EncounterFile
from models import IMAGE_DIR, PDF_DIR
from process_pdfs import DR_PDF_DIR, GLAUCOMA_PDF_DIR

# --- File Directory Mapping ---
# Maps a string identifier to the actual Path object for file serving
FILE_DIRECTORIES = {
    "image": IMAGE_DIR,
    "pdf": PDF_DIR,
    "dr_pdf": DR_PDF_DIR,
    "glaucoma_pdf": GLAUCOMA_PDF_DIR,
}

# --- Pydantic Models for API Response ---
# These models define the structure of the JSON data that your API will return.
# They are mapped to your SQLAlchemy ORM models.

class DiabeticRetinopathyReportSchema(BaseModel):
    """Pydantic model for DiabeticRetinopathyReport table."""
    id: int
    result: str
    qualitative_result: Optional[str] = None
    report_file_name: Optional[str] = None
    report_file_url: Optional[str] = None # Dynamic URL for the report PDF

    class Config:
        from_attributes = True

class GlaucomaReportSchema(BaseModel):
    """Pydantic model for GlaucomaReport table."""
    id: int
    vcdr_right: Optional[str] = None
    vcdr_left: Optional[str] = None
    result: str
    qualitative_result: Optional[str] = None
    report_file_name: Optional[str] = None
    report_file_url: Optional[str] = None # Dynamic URL for the report PDF

    class Config:
        from_attributes = True

class EncounterFileSchema(BaseModel):
    """Pydantic model for EncounterFile table (images, PDFs)."""
    id: int
    filename: str
    file_type: str
    ocr_processed: bool
    file_url: Optional[str] = None # Dynamic URL for the file

    class Config:
        from_attributes = True

class PatientEncounterSchema(BaseModel):
    """
    Pydantic model for a single PatientEncounter, including related reports and files.
    Now includes a self-referential detail_url for this specific encounter.
    This schema is used for detailed views where all information, including files, is needed.
    """
    id: int
    name: str
    patient_id: str
    capture_date: str
    detail_url: Optional[str] = None
    
    # Nested Pydantic models for relationships
    dr_reports: List[DiabeticRetinopathyReportSchema] = Field(default_factory=list)
    glaucoma_reports: List[GlaucomaReportSchema] = Field(default_factory=list)
    encounter_files: List[EncounterFileSchema] = Field(default_factory=list)

    class Config:
        from_attributes = True

class PatientEncounterListSchema(BaseModel):
    """
    Pydantic model for a patient encounter when listed in summary.
    Excludes encounter_files for a faster return on list views.
    """
    id: int
    name: str
    patient_id: str
    capture_date: str
    detail_url: Optional[str] = None
    
    dr_reports: List[DiabeticRetinopathyReportSchema] = Field(default_factory=list)
    glaucoma_reports: List[GlaucomaReportSchema] = Field(default_factory=list)

    class Config:
        from_attributes = True


# --- FastAPI Application Setup ---
app = FastAPI(
    title="Patient Eye Report API",
    description="API to retrieve patient encounter and eye report data.",
    version="1.0.0"
)

# --- CORS MIDDLEWARE CONFIGURATION ---
origins = [
    "http://localhost",
    "http://localhost:5173",  # Your SvelteKit development server's origin
    "http://127.0.0.1:5173",  # Include if using 127.0.0.1 explicitly
    # Add any other origins where your frontend might be hosted in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency to get a Database Session ---
def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()

# --- API Endpoints ---

@app.get("/patients/", response_model=List[PatientEncounterListSchema])
def get_all_patient_encounters(request: Request, db: DBSession = Depends(get_db)):
    """
    Retrieves a list of all patient encounters, sorted by patient ID and capture date.
    Each encounter includes a link to its individual detail view.
    This endpoint does NOT return individual encounter files for faster retrieval.
    """
    patients_orm = db.query(PatientEncounters).options(
        selectinload(PatientEncounters.dr_reports),
        selectinload(PatientEncounters.glaucoma_reports)
    ).order_by(PatientEncounters.patient_id, PatientEncounters.capture_date).all()
    
    response_data = []
    for patient_orm in patients_orm:
        patient_list_schema_instance = PatientEncounterListSchema.from_orm(patient_orm)
        patient_list_schema_instance.detail_url = f"{request.url.scheme}://{request.url.netloc}/patients/{patient_orm.patient_id}/encounters/{patient_orm.id}"
        
        # Populate report_file_url for DR reports
        for dr_report in patient_list_schema_instance.dr_reports:
            if dr_report.report_file_name:
                dr_report.report_file_url = f"{request.url.scheme}://{request.url.netloc}/files/dr_pdf/{dr_report.report_file_name}"
        
        # Populate report_file_url for Glaucoma reports
        for gl_report in patient_list_schema_instance.glaucoma_reports:
            if gl_report.report_file_name:
                gl_report.report_file_url = f"{request.url.scheme}://{request.url.netloc}/files/glaucoma_pdf/{gl_report.report_file_name}"

        response_data.append(patient_list_schema_instance)
        
    return response_data

@app.get("/patients/{patient_id}/encounters", response_model=List[PatientEncounterSchema])
def get_patient_encounters_by_id(patient_id: str, request: Request, db: DBSession = Depends(get_db)):
    """
    Retrieves all encounters for a specific patient ID, sorted by capture date.
    Each encounter includes its associated reports, files, and a link to its individual detail view.
    """
    encounters = db.query(PatientEncounters).filter(PatientEncounters.patient_id == patient_id).options(
        selectinload(PatientEncounters.dr_reports),
        selectinload(PatientEncounters.glaucoma_reports),
        selectinload(PatientEncounters.encounter_files)
    ).order_by(PatientEncounters.capture_date).all()

    if not encounters:
        raise HTTPException(status_code=404, detail=f"No encounters found for patient ID: {patient_id}")

    response_data = []
    for encounter_orm in encounters:
        encounter_schema_instance = PatientEncounterSchema.from_orm(encounter_orm)
        encounter_schema_instance.detail_url = f"{request.url.scheme}://{request.url.netloc}/patients/{encounter_orm.patient_id}/encounters/{encounter_orm.id}"

        # Populate file_url for EncounterFiles
        for encounter_file in encounter_schema_instance.encounter_files:
            file_type_dir = "image" if encounter_file.file_type == "image" else "pdf"
            encounter_file.file_url = f"{request.url.scheme}://{request.url.netloc}/files/{file_type_dir}/{encounter_file.filename}"

        # Populate report_file_url for DR reports
        for dr_report in encounter_schema_instance.dr_reports:
            if dr_report.report_file_name:
                dr_report.report_file_url = f"{request.url.scheme}://{request.url.netloc}/files/dr_pdf/{dr_report.report_file_name}"
        
        # Populate report_file_url for Glaucoma reports
        for gl_report in encounter_schema_instance.glaucoma_reports:
            if gl_report.report_file_name:
                gl_report.report_file_url = f"{request.url.scheme}://{request.url.netloc}/files/glaucoma_pdf/{gl_report.report_file_name}"

        response_data.append(encounter_schema_instance)
    
    return response_data

@app.get("/patients/{patient_id}/encounters/{encounter_id}", response_model=PatientEncounterSchema)
def get_single_encounter_details(patient_id: str, encounter_id: int, request: Request, db: DBSession = Depends(get_db)):
    """
    Retrieves detailed information for a single patient encounter by its unique ID.
    Includes all associated reports, images, and PDFs.
    Ensures the encounter belongs to the specified patient_id.
    """
    encounter = db.query(PatientEncounters).filter(
        PatientEncounters.id == encounter_id,
        PatientEncounters.patient_id == patient_id
    ).options(
        selectinload(PatientEncounters.dr_reports),
        selectinload(PatientEncounters.glaucoma_reports),
        selectinload(PatientEncounters.encounter_files)
    ).first()

    if not encounter:
        raise HTTPException(status_code=404, detail=f"Encounter ID {encounter_id} not found for patient ID {patient_id}")

    encounter_schema_instance = PatientEncounterSchema.from_orm(encounter)
    encounter_schema_instance.detail_url = f"{request.url.scheme}://{request.url.netloc}/patients/{encounter.patient_id}/encounters/{encounter.id}"

    # Populate file_url for EncounterFiles within the detailed view
    for encounter_file in encounter_schema_instance.encounter_files:
        file_type_dir = "image" if encounter_file.file_type == "image" else "pdf"
        encounter_file.file_url = f"{request.url.scheme}://{request.url.netloc}/files/{file_type_dir}/{encounter_file.filename}"

    # Populate report_file_url for DR reports
    for dr_report in encounter_schema_instance.dr_reports:
        if dr_report.report_file_name:
            dr_report.report_file_url = f"{request.url.scheme}://{request.url.netloc}/files/dr_pdf/{dr_report.report_file_name}"
    
    # Populate report_file_url for Glaucoma reports
    for gl_report in encounter_schema_instance.glaucoma_reports:
        if gl_report.report_file_name:
            gl_report.report_file_url = f"{request.url.scheme}://{request.url.netloc}/files/glaucoma_pdf/{gl_report.report_file_name}"

    return encounter_schema_instance

# NEW: Endpoint to serve files
@app.get("/files/{file_type}/{filename}")
async def serve_file(file_type: str, filename: str):
    """
    Serves a file (image or PDF) from the specified directory.
    Validates file type and path to prevent directory traversal.
    """
    base_dir = FILE_DIRECTORIES.get(file_type)

    if not base_dir:
        raise HTTPException(status_code=404, detail="Invalid file type.")

    file_path = base_dir / filename

    # Fixed: Use Path.is_relative_to() for path validation
    if not file_path.is_file() or not file_path.is_relative_to(base_dir):
        raise HTTPException(status_code=404, detail="File not found or unauthorized access.")
    
    # Determine media type based on file extension for proper browser rendering
    media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "image/jpeg" # Default for images, adjust as needed

    return FileResponse(file_path, media_type=media_type)
