import re
import io
from pathlib import Path

# --- OCR Imports ---
try:
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image
    OCR_ENABLED = True
except ImportError:
    OCR_ENABLED = False

# --- Model and DB Imports ---
# Import everything needed from the new models.py file
from models import (
    Base,
    EncounterFile,
    DiabeticRetinopathyReport,
    GlaucomaReport,
    engine,
    Session,
    PDF_DIR
)

# --- Tesseract Configuration ---
# If Tesseract is not in your system's PATH, you may need to set its location manually.
# For example, on Windows:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# --- OCR Processing ---

def extract_dr_data(text, session, encounter_file):
    """Extracts data from a Diabetic Retinopathy report text."""
    match = re.search(r"Result DR:\s*(.*)", text, re.IGNORECASE | re.DOTALL)
    if match:
        result = match.group(1).strip().split('\n')[0] # Take first line of the result
        # Check if a report for this encounter already exists to avoid duplicates
        existing_report = session.query(DiabeticRetinopathyReport).filter_by(patient_encounter_id=encounter_file.patient_encounter_id).first()
        if not existing_report:
            report = DiabeticRetinopathyReport(patient_encounter_id=encounter_file.patient_encounter_id, result=result)
            session.add(report)
        print(f"    - Extracted DR Result: {result}")

def extract_glaucoma_data(text, session, encounter_file):
    """Extracts data from a Glaucoma report text by focusing on the SCREENING RESULT section."""
    vcdr_right = None
    vcdr_left = None
    result = "N/A"

    # Try to find the SCREENING RESULT section to narrow down the search
    screening_section_match = re.search(r"SCREENING RESULT\s*(.*)", text, re.IGNORECASE | re.DOTALL)
    if screening_section_match:
        section_text = screening_section_match.group(1)
        
        # Find all VCDR values within that section
        vcdr_values = re.findall(r"VCDR\s*-\s*([0-9.]+)", section_text, re.IGNORECASE)
        if len(vcdr_values) >= 2:
            vcdr_right = float(vcdr_values[0])
            vcdr_left = float(vcdr_values[1])
        elif len(vcdr_values) == 1:
            # If only one value, check if it's associated with left or right
            if 'left eye' in section_text.lower():
                vcdr_left = float(vcdr_values[0])
            else:
                vcdr_right = float(vcdr_values[0])

        # Extract the result text from the section
        result_match = re.search(r"(No Referable Glaucoma|Referable Glaucoma|Referable Glacuoma)\s*-\s*(.*)", section_text, re.IGNORECASE)
        if result_match:
            result = result_match.group(0).strip()

    # Check if a report for this encounter already exists to prevent duplicates
    existing_report = session.query(GlaucomaReport).filter_by(patient_encounter_id=encounter_file.patient_encounter_id).first()
    if not existing_report:
        report = GlaucomaReport(
            patient_encounter_id=encounter_file.patient_encounter_id,
            vcdr_right=vcdr_right,
            vcdr_left=vcdr_left,
            result=result
        )
        session.add(report)
    
    # Always print what was found, even if it's None
    print(f"    - Extracted Glaucoma VCDR Right: {vcdr_right}")
    print(f"    - Extracted Glaucoma VCDR Left: {vcdr_left}")
    print(f"    - Extracted Glaucoma Result: {result}")


def process_pdf_files(session):
    """Processes all PDF files found in the database."""
    if not OCR_ENABLED:
        print("\nSkipping PDF processing: OCR libraries not found.")
        print("Please install them using: pip install pytesseract \"PyMuPDF<1.24.0\" Pillow")
        return

    print("\n--- Starting PDF OCR Processing ---")
    
    # Query all PDF files from the database, not just unprocessed ones.
    all_pdfs = session.query(EncounterFile).filter_by(file_type='pdf').all()
    if not all_pdfs:
        print("No PDFs found in the database to process.")
        return

    for encounter_file in all_pdfs:
        pdf_path = PDF_DIR / encounter_file.filename
        if not pdf_path.exists():
            print(f"PDF not found: {pdf_path}. Skipping.")
            continue
        
        print(f"\n=======================================================")
        print(f"  Processing PDF: {encounter_file.filename}")
        print(f"=======================================================")
        try:
            doc = fitz.open(pdf_path)
            # A single PDF file can contain multiple reports, so we check each page
            for page_num, page in enumerate(doc):
                print(f"\n---------- Page {page_num + 1} Full OCR Text ----------")
                pix = page.get_pixmap(dpi=300) # Higher DPI for better OCR
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                
                text = pytesseract.image_to_string(img)
                print(text)
                print("--------------------------------------------")
                print("\n    >>> Extracting structured data from page...")

                if "Diabetic Retinopathy Report" in text:
                    extract_dr_data(text, session, encounter_file)
                
                if "Glaucoma Screening Report" in text:
                    extract_glaucoma_data(text, session, encounter_file)
            
            # Commit any new reports to the database for this file
            session.commit()
            print(f"\n  Finished processing for: {encounter_file.filename}")

        except Exception as e:
            print(f"  An error occurred during OCR for {encounter_file.filename}: {e}")
            session.rollback()

    print("\n--- PDF OCR Processing Finished ---")

# --- Main Execution ---

def main():
    """Main function to run the OCR workflow."""
    print("Starting PDF OCR processing workflow...")
    
    # Create tables if they don't exist
    Base.metadata.create_all(engine)
    
    session = Session()

    process_pdf_files(session)

    session.close()
    print("\nWorkflow finished.")


if __name__ == "__main__":
    main()
