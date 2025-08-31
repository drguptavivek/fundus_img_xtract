#main.py
import os
import zipfile
import hashlib
import re
import shutil
from pathlib import Path
from datetime import datetime, date as _date
from dotenv import load_dotenv  
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
MALICIOUS_LOG_FILE = BASE_DIR / os.getenv("MALICIOUS_UPLOAD_LOG", "logs/malicious_uploads.log")

# Only allow these extensions inside uploaded ZIPs
ALLOWED_EXTS = {".pdf", ".jpg", ".jpeg"}


class MaliciousZipError(Exception):
    """Raised when a ZIP contains disallowed files or paths."""
    pass


def _sniff_member_type(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    """Best-effort magic-bytes sniffing.
    Returns one of: 'pdf', 'jpg', 'pe', 'elf', 'zip', 'script', 'unknown'.
    """
    try:
        with zf.open(info) as fp:
            head = fp.read(8)
    except Exception:
        return "unknown"
    if head.startswith(b"%PDF-"):
        return "pdf"
    # JPEG SOI marker FFD8FF
    if len(head) >= 3 and head[:3] == b"\xFF\xD8\xFF":
        return "jpg"
    if head[:2] == b"MZ":
        return "pe"
    if head[:4] == b"\x7FELF":
        return "elf"
    if head[:2] == b"PK":
        return "zip"
    if head[:2] == b"#!":
        return "script"
    return "unknown"


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


def parse_capture_date(s: str | None) -> _date | None:
    if not s:
        return None
    s = str(s).strip()
    # Try common formats first
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%m-%d-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


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
def process_zip_file(zip_path: Path, session) -> list[str]:
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
    deleted_zip = False  # if we delete due to disallowed content, skip any move
    added_pdf_filenames: list[str] = []
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

            # --- Strict allowlist: only PDF and JPG/JPEG files allowed ---
            # Also block path traversal or absolute paths within the ZIP
            for info in zf.infolist():
                if info.is_dir():
                    continue
                inner_name = info.filename
                # Ignore macOS metadata entries inside zips
                if inner_name.startswith("__MACOSX/") or Path(inner_name).name.startswith("._"):
                    continue
                # Block absolute paths and traversal like ../
                p = Path(inner_name)
                if inner_name.startswith("/") or any(part == ".." for part in p.parts):
                    print(f"  Disallowed path in archive: {inner_name}")
                    zf.close()
                    # Log malicious upload with user & IP from sidecar metadata, if available
                    try:
                        meta_dir = UPLOAD_DIR.parent / "upload_meta"
                        meta_path = meta_dir / f"{zip_path.name}.json"
                        uploader_username = "-"
                        uploader_ip = "-"
                        if meta_path.exists():
                            import json
                            with open(meta_path, "r", encoding="utf-8") as mf:
                                meta = json.load(mf)
                                uploader_username = meta.get("uploader_username", "-")
                                uploader_ip = meta.get("ip", "-")
                        MALICIOUS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                        with open(MALICIOUS_LOG_FILE, "a", encoding="utf-8") as lf:
                            from datetime import datetime as _dt
                            ts = _dt.utcnow().isoformat() + "Z"
                            lf.write(f"[{ts}] zip={zip_path.name} user={uploader_username} ip={uploader_ip} reason=path_traversal entry={inner_name}\n")
                    except Exception:
                        pass
                    try:
                        zip_path.unlink()
                        deleted_zip = True
                        # best-effort: remove sidecar metadata
                        try:
                            (UPLOAD_DIR.parent / "upload_meta" / f"{zip_path.name}.json").unlink(missing_ok=True)
                        except Exception:
                            pass
                    except Exception as _e:
                        print(f"  Failed to delete disallowed ZIP '{zip_path.name}': {_e}")
                    log_status(zip_path.name, "DELETED_BADZIP", "path traversal or absolute path detected")
                    raise MaliciousZipError("Rejected: path traversal or absolute path detected")
                ext = p.suffix.lower()
                if ext not in ALLOWED_EXTS:
                    print(f"  Disallowed file type in archive: {inner_name}")
                    zf.close()
                    # Log malicious upload with user & IP from sidecar metadata, if available
                    try:
                        meta_dir = UPLOAD_DIR.parent / "upload_meta"
                        meta_path = meta_dir / f"{zip_path.name}.json"
                        uploader_username = "-"
                        uploader_ip = "-"
                        if meta_path.exists():
                            import json
                            with open(meta_path, "r", encoding="utf-8") as mf:
                                meta = json.load(mf)
                                uploader_username = meta.get("uploader_username", "-")
                                uploader_ip = meta.get("ip", "-")
                        MALICIOUS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                        with open(MALICIOUS_LOG_FILE, "a", encoding="utf-8") as lf:
                            from datetime import datetime as _dt
                            ts = _dt.utcnow().isoformat() + "Z"
                            lf.write(f"[{ts}] zip={zip_path.name} user={uploader_username} ip={uploader_ip} reason=disallowed_file entry={inner_name}\n")
                    except Exception:
                        pass
                    try:
                        zip_path.unlink()
                        deleted_zip = True
                        # best-effort: remove sidecar metadata
                        try:
                            (UPLOAD_DIR.parent / "upload_meta" / f"{zip_path.name}.json").unlink(missing_ok=True)
                        except Exception:
                            pass
                    except Exception as _e:
                        print(f"  Failed to delete disallowed ZIP '{zip_path.name}': {_e}")
                    log_status(zip_path.name, "DELETED_BADZIP", f"disallowed entry: {inner_name}")
                    # Set explicit detail for job item
                    raise MaliciousZipError(f"Disallowed file type in archive: {inner_name}")

                # Content-type sniffing to catch renamed executables/scripts
                detected = _sniff_member_type(zf, info)
                expected = 'pdf' if ext == '.pdf' else ('jpg' if ext in {'.jpg', '.jpeg'} else 'unknown')
                if expected == 'pdf' and detected != 'pdf':
                    print(f"  Type mismatch for {inner_name}: ext={ext} detected={detected}")
                    zf.close()
                    try:
                        meta_dir = UPLOAD_DIR.parent / "upload_meta"
                        meta_path = meta_dir / f"{zip_path.name}.json"
                        uploader_username = "-"
                        uploader_ip = "-"
                        if meta_path.exists():
                            import json
                            with open(meta_path, "r", encoding="utf-8") as mf:
                                meta = json.load(mf)
                                uploader_username = meta.get("uploader_username", "-")
                                uploader_ip = meta.get("ip", "-")
                        MALICIOUS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                        with open(MALICIOUS_LOG_FILE, "a", encoding="utf-8") as lf:
                            from datetime import datetime as _dt
                            ts = _dt.utcnow().isoformat() + "Z"
                            lf.write(f"[{ts}] zip={zip_path.name} user={uploader_username} ip={uploader_ip} reason=type_mismatch expected=pdf detected={detected} entry={inner_name}\n")
                    except Exception:
                        pass
                    try:
                        zip_path.unlink()
                        deleted_zip = True
                        try:
                            (UPLOAD_DIR.parent / "upload_meta" / f"{zip_path.name}.json").unlink(missing_ok=True)
                        except Exception:
                            pass
                    except Exception as _e:
                        print(f"  Failed to delete disallowed ZIP '{zip_path.name}': {_e}")
                    log_status(zip_path.name, "DELETED_BADZIP", f"type mismatch: expected pdf, detected {detected} ({inner_name})")
                    raise MaliciousZipError(f"Rejected: extension/content mismatch — expected PDF, detected {detected} (entry: {inner_name})")
                if expected == 'jpg' and detected != 'jpg':
                    print(f"  Type mismatch for {inner_name}: ext={ext} detected={detected}")
                    zf.close()
                    try:
                        meta_dir = UPLOAD_DIR.parent / "upload_meta"
                        meta_path = meta_dir / f"{zip_path.name}.json"
                        uploader_username = "-"
                        uploader_ip = "-"
                        if meta_path.exists():
                            import json
                            with open(meta_path, "r", encoding="utf-8") as mf:
                                meta = json.load(mf)
                                uploader_username = meta.get("uploader_username", "-")
                                uploader_ip = meta.get("ip", "-")
                        MALICIOUS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                        with open(MALICIOUS_LOG_FILE, "a", encoding="utf-8") as lf:
                            from datetime import datetime as _dt
                            ts = _dt.utcnow().isoformat() + "Z"
                            lf.write(f"[{ts}] zip={zip_path.name} user={uploader_username} ip={uploader_ip} reason=type_mismatch expected=jpg detected={detected} entry={inner_name}\n")
                    except Exception:
                        pass
                    try:
                        zip_path.unlink()
                        deleted_zip = True
                        try:
                            (UPLOAD_DIR.parent / "upload_meta" / f"{zip_path.name}.json").unlink(missing_ok=True)
                        except Exception:
                            pass
                    except Exception as _e:
                        print(f"  Failed to delete disallowed ZIP '{zip_path.name}': {_e}")
                    log_status(zip_path.name, "DELETED_BADZIP", f"type mismatch: expected jpg, detected {detected} ({inner_name})")
                    raise MaliciousZipError(f"Rejected: extension/content mismatch — expected JPG, detected {detected} (entry: {inner_name})")

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
                name=name,
                patient_id=patient_id,
                capture_date=capture_date,
            )
            # Populate proper Date column when possible
            parsed_dt = parse_capture_date(capture_date)
            if parsed_dt is not None:
                new_patient_encounter.capture_date_dt = parsed_dt
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

                # Only allow JPG/JPEG images and PDFs (as per requirement)
                if ext in {'.jpg', '.jpeg'}:
                    dest_dir, file_type = IMAGE_DIR, 'image'
                elif ext == '.pdf':
                    dest_dir, file_type = PDF_DIR, 'pdf'
                else:
                    # Should not reach here due to pre-check, but keep defensive
                    continue

                target_path = dest_dir / new_filename
                # Ensure both source and target are closed promptly
                with zf.open(member_info) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)

                files_to_add.append(EncounterFile(filename=new_filename, file_type=file_type, uuid=str(uuid4())))
                if file_type == 'pdf':
                    added_pdf_filenames.append(new_filename)
                print(f"  - Extracted and renamed '{original_filepath.name}' to '{new_filename}'")

            new_patient_encounter.encounter_files = files_to_add
            session.add(new_zip_file)

        # --- OUTSIDE the with-block: the ZIP file handle is closed now ---
        session.commit()
        success = True
        print(f"Successfully processed and logged '{zip_path.name}'.")
        return added_pdf_filenames

    except (zipfile.BadZipFile, ValueError) as e:
        print(f"Error processing '{zip_path.name}': {e}")
        session.rollback()
        success = False
        error_message = str(e)
        # Treat structural/format errors as hard failures for job items
        raise
    except MaliciousZipError as e:
        # Propagate to caller so /jobs item shows explicit rejection reason
        print(f"Rejected malicious ZIP '{zip_path.name}': {e}")
        session.rollback()
        success = False
        error_message = str(e)
        # Re-raise so worker records item state=error with detail
        raise
    except Exception as e:
        print(f"Error processing '{zip_path.name}': {e}")
        session.rollback()
        success = False
        error_message = str(e)
        raise
    finally:
        try:
            if deleted_zip:
                # Already deleted due to disallowed content; nothing to move
                pass
            elif success:
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
        # Do not return here; allow previous return or raised exceptions to propagate

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
