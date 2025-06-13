import os
import zipfile
import hashlib
import re
import shutil
from pathlib import Path

# --- Model and DB Imports ---
# Import everything needed from the new models.py file
from models import (
    Base,
    ZipFile,
    PatientEncounters,
    EncounterFile,
    engine,
    Session,
    UPLOAD_DIR,
    IMAGE_DIR,
    PDF_DIR,
    PROCESSED_DIR,
    PROCESSING_ERROR_DIR
)

# --- Utility Functions ---

def setup_environment():
    """Creates the necessary directories for the script to run."""
    print("Setting up the environment...")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSING_ERROR_DIR.mkdir(parents=True, exist_ok=True)
    print("Directories are ready.")

def setup_database():
    """Initializes the database and creates tables from the SQLAlchemy models."""
    print("Setting up the database...")
    Base.metadata.create_all(engine)
    print("Database is ready.")

def calculate_md5(filepath):
    """Calculates the MD5 hash of a file for unique identification."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

# --- Main Processing Logic ---

def process_zip_file(zip_path, session):
    """
    Processes a single ZIP file, extracts metadata, and organizes files.
    """
    md5_hash = calculate_md5(zip_path)
    if session.query(ZipFile).filter_by(md5_hash=md5_hash).first():
        print(f"Skipping '{zip_path.name}', as it has already been processed.")
        return

    print(f"\n--- Processing '{zip_path.name}' ---")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            print("  Archive Contents (Tree Structure):")
            zf.printdir()
            print("-" * 40)

            dir_in_zip = None
            all_dirs = {Path(p).parent for p in zf.namelist()}
            
            for d in all_dirs:
                current_path = Path(d)
                for i in range(len(current_path.parts)):
                    test_path_str = '/'.join(current_path.parts[:i+1])
                    dir_parts = test_path_str.split('_')
                    if len(dir_parts) >= 3:
                        dir_in_zip = Path(test_path_str)
                        break
                if dir_in_zip:
                    break

            if not dir_in_zip:
                raise ValueError("No directory matching the 'Name_ID_Date' format found.")

            dir_parts = dir_in_zip.name.rstrip('/').split('_')
            capture_date = dir_parts[-1]
            patient_id = dir_parts[-2]
            name = ' '.join(dir_parts[:-2])

            new_zip_file = ZipFile(zip_filename=zip_path.name, md5_hash=md5_hash)
            new_patient_encounter = PatientEncounters(
                name=name, patient_id=patient_id, capture_date=capture_date
            )
            new_zip_file.patient_encounter = new_patient_encounter

            print(f"  Identified Parent Directory: {dir_in_zip.name}")
            print(f"  Extracted Info -> Name: {name}, Patient ID: {patient_id}, Capture Date: {capture_date}")

            files_to_add = []
            for member_info in zf.infolist():
                if member_info.is_dir() or not str(Path(member_info.filename)).startswith(str(dir_in_zip)):
                    continue

                original_filepath = Path(member_info.filename)
                file_ext = original_filepath.suffix.lower()
                new_filename = f"{patient_id}_{name.replace(' ', '_')}_{capture_date}_{original_filepath.name.replace('/', '_')}"
                
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                    dest_dir, file_type = IMAGE_DIR, 'image'
                elif file_ext == '.pdf':
                    dest_dir, file_type = PDF_DIR, 'pdf'
                else:
                    continue

                source = zf.open(member_info)
                target_path = dest_dir / new_filename
                with open(target_path, "wb") as target:
                    target.write(source.read())
                
                files_to_add.append(EncounterFile(filename=new_filename, file_type=file_type))
                print(f"  - Extracted and renamed '{original_filepath.name}' to '{new_filename}'")
            
            new_patient_encounter.encounter_files = files_to_add
            session.add(new_zip_file)
            session.commit()

            print(f"Successfully processed and logged '{zip_path.name}'.")
            shutil.move(zip_path, PROCESSED_DIR / zip_path.name)
            print(f"Moved '{zip_path.name}' to processed directory.")

    except (zipfile.BadZipFile, ValueError, Exception) as e:
        print(f"Error processing '{zip_path.name}': {e}")
        session.rollback()
        shutil.move(zip_path, PROCESSING_ERROR_DIR / zip_path.name)
        print(f"Moved '{zip_path.name}' to error directory.")

# --- Main Execution ---

def main():
    """Main function to run the entire workflow."""
    print("Starting ZIP file processing workflow...")
    setup_environment()
    setup_database()
    
    session = Session()

    zip_files = list(UPLOAD_DIR.glob("*.zip"))
    if not zip_files:
        print("\nNo new ZIP files found in 'files/uploaded'.")
    else:
        for zip_path in zip_files:
            process_zip_file(zip_path, session)

    session.close()
    print("\nWorkflow finished.")


if __name__ == "__main__":
    main()
