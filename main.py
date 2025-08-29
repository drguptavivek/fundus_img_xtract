#main.py
import os
import zipfile
import hashlib
import re
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv  # ✅ load .env first
load_dotenv()



# --- Model and DB Imports ---
# Import everything needed from the new models.py file
from models import (
    Base,
    ZipFile,
    PatientEncounters,
    EncounterFile,
    engine,
    Session,
    BASE_DIR, 
    UPLOAD_DIR,
    IMAGE_DIR,
    PDF_DIR,
    PROCESSED_DIR,
    PROCESSING_ERROR_DIR,
)
from uuid import uuid4

# Path for log file
LOG_FILE = BASE_DIR / os.getenv("ZIP_INGEST_LOG", "logs/zip_main_process_log.txt")


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
    print("Setting up the database...", flush=True)
    Base.metadata.create_all(engine)

    print("Database is ready.", flush=True)

def calculate_md5(filepath):
    """Calculates the MD5 hash of a file for unique identification."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def clean_filename(name: str) -> str:
    # Remove Windows duplicate suffixes like " (1)" or " (2)"
    return re.sub(r"\s\(\d+\)", "", name)





def log_status(filename: str, status: str, message: str = ""):
    """Append a processing status entry to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {filename} -> {status}"
    if message:
        log_entry += f" | {message}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")
    print(f"LOG: {log_entry}")  # also print for console feedback


def daily_dup_dir() -> Path:
    # /files/dupmd5_YYYY-MM-DD
    files_root = UPLOAD_DIR.parent
    ddir = files_root / f"dupmd5_{datetime.now():%Y-%m-%d}"
    ddir.mkdir(parents=True, exist_ok=True)
    return ddir


# --- Main Processing Logic ---
def process_zip_file(zip_path: Path, session):
    """
    Processes a single ZIP file, extracts metadata, and organizes files.
    Ensures the ZIP file is CLOSED before attempting to move it.
    """
    def safe_move(src: Path, dst: Path, attempts: int = 5):
        # Small retry helper for Windows lock shenanigans
        import time
        for i in range(attempts):
            try:
                shutil.move(str(src), str(dst))
                return
            except PermissionError as e:
                if i == attempts - 1:
                    raise
                time.sleep(0.2 * (i + 1))

    md5_hash = calculate_md5(zip_path)
    existing = session.query(ZipFile).filter_by(md5_hash=md5_hash).first()
    if existing:
        # Found duplicate content
        original_name = existing.zip_filename  # first-seen file with this MD5
        dup_dir = daily_dup_dir()

        try:
            shutil.move(str(zip_path), str(dup_dir / zip_path.name))
            print(f"Duplicate '{zip_path.name}' moved to '{dup_dir}'.")
        except PermissionError as e:
            print(f"Failed to move duplicate '{zip_path.name}': {e}")

        log_status(zip_path.name, "SKIPPED_DUPMD5", f"original={original_name}")
        return

    print(f"\n--- Processing '{zip_path.name}' ---")

    success = False  # track outcome to decide where to move the ZIP
    error_message = ""

    try:
        # --- OPEN ZIP (everything that reads from the archive stays inside this block) ---
        # Guard: skip macOS resource fork artifacts and invalid zips
        if zip_path.name.startswith("._"):
            print(f"Skipping resource-fork file '{zip_path.name}'.")
            log_status(zip_path.name, "SKIPPED_RESOURCEFORK")
            return
        if not zipfile.is_zipfile(zip_path):
            print(f"File '{zip_path.name}' is not a valid ZIP. Moving to error.")
            try:
                # define a local mover consistent with below
                def _safe_move_local(src: Path, dst: Path):
                    import time
                    for i in range(5):
                        try:
                            shutil.move(str(src), str(dst))
                            return
                        except PermissionError as _:
                            if i == 4:
                                raise
                            time.sleep(0.2 * (i + 1))
                _safe_move_local(zip_path, PROCESSING_ERROR_DIR / zip_path.name)
            except PermissionError as pe:
                print(f"Final move failed for '{zip_path.name}' due to a lock: {pe}.")
            log_status(zip_path.name, "ERROR_BADZIP", "not a zip file")
            return

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


            clean_name = clean_filename(zip_path.name)
            new_zip_file = ZipFile(zip_filename=clean_name, md5_hash=md5_hash)
            new_patient_encounter = PatientEncounters(
                name=name, patient_id=patient_id, capture_date=capture_date
            )
            new_zip_file.patient_encounter = new_patient_encounter

            print(f"  Identified Parent Directory: {dir_in_zip.name}")
            print(f"  Extracted Info -> Name: {name}, Patient ID: {patient_id}, Capture Date: {capture_date}")

            files_to_add = []
            for member_info in zf.infolist():
                # skip directories or items outside the identified parent dir
                if member_info.is_dir() or not str(Path(member_info.filename)).startswith(str(dir_in_zip)):
                    continue

                original_filepath = Path(member_info.filename)
                ext = original_filepath.suffix.lower()
                new_filename = f"{patient_id}_{name.replace(' ', '_')}_{capture_date}_{original_filepath.name.replace('/', '_')}"

                if ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}:
                    dest_dir, file_type = IMAGE_DIR, 'image'
                elif ext == '.pdf':
                    dest_dir, file_type = PDF_DIR, 'pdf'
                else:
                    continue

                target_path = dest_dir / new_filename
                # Ensure both source and target are closed promptly
                with zf.open(member_info) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)

                files_to_add.append(EncounterFile(filename=new_filename, file_type=file_type, uuid=str(uuid4())))
                print(f"  - Extracted and renamed '{original_filepath.name}' to '{new_filename}'")

            new_patient_encounter.encounter_files = files_to_add
            session.add(new_zip_file)

        # --- OUTSIDE the with-block: the ZIP file handle is closed now ---
        session.commit()
        success = True
        print(f"Successfully processed and logged '{zip_path.name}'.")

    except (zipfile.BadZipFile, ValueError) as e:
        print(f"Error processing '{zip_path.name}': {e}")
        session.rollback()
        success = False
        error_message = str(e)
    except Exception as e:
        print(f"Error processing '{zip_path.name}': {e}")
        session.rollback()
        success = False
        error_message = str(e)
    finally:
        try:
            if success:
                safe_move(zip_path, PROCESSED_DIR / zip_path.name)
                print(f"Moved '{zip_path.name}' to processed directory.")
                log_status(zip_path.name, "SUCCESS")
            else:
                safe_move(zip_path, PROCESSING_ERROR_DIR / zip_path.name)
                print(f"Moved '{zip_path.name}' to error directory.")
                log_status(zip_path.name, "ERROR", error_message or "")
        except PermissionError as pe:
            # If it’s still locked by some external process, surface a clear message
            print(f"Final move failed for '{zip_path.name}' due to a lock: {pe}. "
                  f"Please close any apps using this file and rerun.")
            log_status(zip_path.name, "ERROR", f"PermissionError: {pe}")

# --- Main Execution ---

def main():
    """Main function to run the entire workflow."""
    print("Starting ZIP file processing workflow...")
    setup_environment()
    setup_database()
    
    session = Session()

    # Filter out macOS resource fork artifacts like '._*.zip'
    zip_files = [p for p in UPLOAD_DIR.glob("*.zip") if not p.name.startswith("._")]
    if not zip_files:
        print("\nNo new ZIP files found in 'files/uploaded'.")
    else:
        for zip_path in zip_files:
            process_zip_file(zip_path, session)

    session.close()
    print("\nWorkflow finished.")


if __name__ == "__main__":
    main()
