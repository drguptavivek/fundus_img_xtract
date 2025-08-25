import re
from pathlib import Path
from sqlalchemy.orm import Session as DBSession # Renamed to avoid conflict with `session` variable
from sqlalchemy import create_engine
import fitz # Import PyMuPDF for PDF splitting

# Import database models and configurations
from models import (
    engine,
    Session, # Session factory
    PDF_DIR,
    DiabeticRetinopathyReport,
    GlaucomaReport,
    PatientEncounters,
    EncounterFile,
    Base # Import Base for metadata if needed for direct table creation (though main.py handles it)
)

# Define new directories for split PDFs
DR_PDF_DIR = Path(__file__).resolve().parent / "files/dr_pdfs"
GLAUCOMA_PDF_DIR = Path(__file__).resolve().parent / "files/glaucoma_pdfs"

# Import the OCR extraction function from your separate file
# Make sure your OCR function is in 'ocr_extraction.py' in the same directory
from ocr_extraction import find_report_pages_by_coords_with_grid

# --- Main PDF Processing Logic ---

def process_all_pdfs_for_ocr():
    """
    Iterates through all PDF files in the PDF_DIR, performs OCR,
    stores the extracted results into the database, and
    splits and saves individual report pages to new directories.
    """
    print("Starting PDF OCR processing workflow...")
    db_session: DBSession = Session() # Create a session instance

    # Ensure new split PDF directories exist
    DR_PDF_DIR.mkdir(parents=True, exist_ok=True)
    GLAUCOMA_PDF_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Created directories: {DR_PDF_DIR} and {GLAUCOMA_PDF_DIR}")

    try:
        pdf_files = list(PDF_DIR.glob("*.pdf"))
        if not pdf_files:
            print("\nNo PDF files found in 'files/pdfs' for OCR processing.")
            return

        for pdf_path in pdf_files:
            print(f"\n--- Processing OCR for '{pdf_path.name}' ---")
            
            # Extract patient_id, name, capture_date from the PDF filename
            # Filename format: {patient_id}_{name}_{capture_date}_{original_filepath.name.replace('/', '_')}
            parts = pdf_path.name.split('_')
            if len(parts) < 4:
                print(f"Skipping '{pdf_path.name}': Malformed filename, cannot extract patient ID, name, or date.")
                continue
            
            extracted_patient_id = parts[0]
            
            patient_encounter_from_db = db_session.query(PatientEncounters).filter_by(patient_id=extracted_patient_id).first()

            if not patient_encounter_from_db:
                print(f"Skipping '{pdf_path.name}': Patient encounter not found for ID '{extracted_patient_id}'.")
                continue
            
            # Use data from DB for name and capture_date for consistent naming
            patient_name_for_filename = patient_encounter_from_db.name.replace(' ', '_')
            capture_date_for_filename = patient_encounter_from_db.capture_date


            # Find the corresponding PatientEncounters record
            patient_encounter = patient_encounter_from_db

            # Check if this PDF has already been OCR processed for reports
            # We can check if any DR or Glaucoma reports already exist for this encounter
            existing_dr_report = db_session.query(DiabeticRetinopathyReport).filter_by(patient_encounter_id=patient_encounter.id).first()
            existing_gl_report = db_session.query(GlaucomaReport).filter_by(patient_encounter_id=patient_encounter.id).first()

            if existing_dr_report or existing_gl_report:
                print(f"Reports for patient ID '{extracted_patient_id}' from '{pdf_path.name}' already exist. Skipping OCR.")
                
                # Optionally, update the EncounterFile's ocr_processed flag if not already set
                encounter_file = db_session.query(EncounterFile).filter_by(
                    patient_encounter_id=patient_encounter.id, filename=pdf_path.name
                ).first()
                if encounter_file and not encounter_file.ocr_processed:
                    encounter_file.ocr_processed = True
                    db_session.add(encounter_file)
                    db_session.commit()
                    print(f"Updated ocr_processed flag for '{pdf_path.name}'.")
                continue


            # Perform OCR extraction
            (pageNumberDiabeticReport, pageNumberGlaucomaReport,
             text_diabetic_result, text_diabetic_qual_result,
             text_glaucoma_result, vcdr_rt, vcdr_lt, text_gl_qual_result) = \
                find_report_pages_by_coords_with_grid(str(pdf_path)) # find_report_pages_by_coords_with_grid expects string path

            # Open the PDF for splitting if any report page is found
            pdf_document = None
            if pageNumberDiabeticReport is not None or pageNumberGlaucomaReport is not None:
                try:
                    pdf_document = fitz.open(str(pdf_path))
                except Exception as e:
                    print(f"Error opening PDF for splitting '{pdf_path.name}': {e}")
                    pdf_document = None # Ensure it's None if opening failed

            # Initialize filenames for split PDFs
            dr_pdf_filename = None
            gl_pdf_filename = None

            # Process and store Diabetic Retinopathy Report if found
            if pageNumberDiabeticReport is not None:
                if pdf_document:
                    try:
                        # Pages are 0-indexed in PyMuPDF, so subtract 1 from pageNumberDiabeticReport
                        output_dr_pdf = fitz.open() # Create new PDF
                        output_dr_pdf.insert_pdf(pdf_document, from_page=pageNumberDiabeticReport - 1, to_page=pageNumberDiabeticReport - 1)
                        
                        dr_pdf_filename = f"{extracted_patient_id}_{patient_name_for_filename}_{capture_date_for_filename}_DR_Page{pageNumberDiabeticReport}.pdf"
                        dr_pdf_path = DR_PDF_DIR / dr_pdf_filename
                        output_dr_pdf.save(dr_pdf_path)
                        output_dr_pdf.close()
                        print(f"  Saved DR report page {pageNumberDiabeticReport} to '{dr_pdf_path.name}'.")
                    except Exception as e:
                        print(f"  Error saving DR report page {pageNumberDiabeticReport} for '{pdf_path.name}': {e}")

                new_dr_report = DiabeticRetinopathyReport(
                    patient_encounter_id=patient_encounter.id,
                    result=text_diabetic_result, # Directly use OCR output
                    qualitative_result=text_diabetic_qual_result, # Store qualitative result
                    report_file_name=dr_pdf_filename # Store the name of the split DR PDF
                )
                db_session.add(new_dr_report)
                print(f"  Added Diabetic Retinopathy Report for {patient_encounter.name}.")

            # Process and store Glaucoma Report if found
            if pageNumberGlaucomaReport is not None:
                if pdf_document:
                    try:
                        # Pages are 0-indexed in PyMuPDF, so subtract 1 from pageNumberGlaucomaReport
                        output_gl_pdf = fitz.open() # Create new PDF
                        output_gl_pdf.insert_pdf(pdf_document, from_page=pageNumberGlaucomaReport - 1, to_page=pageNumberGlaucomaReport - 1)
                        
                        gl_pdf_filename = f"{extracted_patient_id}_{patient_name_for_filename}_{capture_date_for_filename}_GL_Page{pageNumberGlaucomaReport}.pdf"
                        gl_pdf_path = GLAUCOMA_PDF_DIR / gl_pdf_filename
                        output_gl_pdf.save(gl_pdf_path)
                        output_gl_pdf.close()
                        print(f"  Saved Glaucoma report page {pageNumberGlaucomaReport} to '{gl_pdf_path.name}'.")
                    except Exception as e:
                        print(f"  Error saving Glaucoma report page {pageNumberGlaucomaReport} for '{pdf_path.name}': {e}")

                new_glaucoma_report = GlaucomaReport(
                    patient_encounter_id=patient_encounter.id,
                    vcdr_right=vcdr_rt, # Directly use string OCR output
                    vcdr_left=vcdr_lt,  # Directly use string OCR output
                    result=text_glaucoma_result, # Directly use OCR output
                    qualitative_result=text_gl_qual_result, # Store qualitative result
                    report_file_name=gl_pdf_filename # Store the name of the split Glaucoma PDF
                )
                db_session.add(new_glaucoma_report)
                print(f"  Added Glaucoma Report for {patient_encounter.name}.")
                if vcdr_rt is not None:
                    print(f"    VCDR Right: {vcdr_rt}")
                if vcdr_lt is not None:
                    print(f"    VCDR Left: {vcdr_lt}")
            
            # Close the original PDF document after processing all relevant pages
            if pdf_document:
                pdf_document.close()

            # Update the ocr_processed flag for the specific PDF file
            # This is important to know which files have had their OCR extracted and stored
            encounter_file = db_session.query(EncounterFile).filter_by(
                patient_encounter_id=patient_encounter.id, filename=pdf_path.name
            ).first()

            if encounter_file:
                encounter_file.ocr_processed = True
                db_session.add(encounter_file)
                print(f"  Marked '{pdf_path.name}' as OCR processed in EncounterFile.")
            else:
                print(f"  Warning: Could not find EncounterFile entry for '{pdf_path.name}'.")

            db_session.commit() # Commit changes for the current PDF

            print(f"Successfully processed OCR and split pages for '{pdf_path.name}'.")

    except Exception as e:
        print(f"An error occurred during PDF OCR processing: {e}")
        db_session.rollback() # Rollback all changes in case of an error
    finally:
        db_session.close() # Always close the session
        print("\nPDF OCR processing workflow finished.")

if __name__ == '__main__':
    process_all_pdfs_for_ocr()
