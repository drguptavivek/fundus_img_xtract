#main.py
import os
import zipfile
import hashlib
import re
import shutil
from pathlib import Path
from datetime import datetime, date as _date

from utils.env_loader import load_environment

load_environment()


# --- Model and DB Imports ---
# Import everything needed from the new models.py file
from models import (
    DR_PDF_DIR,
    GLAUCOMA_PDF_DIR,
    Base,
    ZipFile,
    PatientEncounters,
    EncounterFile,
    EncounterFilePDF,
    Camera,
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

def get_daily_dirs():
    """Get daily subdirectories for organizing files by date."""
    today_str = datetime.now().strftime("%Y_%m_%d")
    
    # Create dated directories
    upload_daily = UPLOAD_DIR / today_str
    processed_daily = PROCESSED_DIR / today_str
    error_daily = PROCESSING_ERROR_DIR / today_str
    image_daily = IMAGE_DIR / today_str
    pdf_daily = PDF_DIR / today_str
    dr_pdf_daily = DR_PDF_DIR / today_str
    glaucoma_pdf_daily = GLAUCOMA_PDF_DIR / today_str
    
    return {
        'upload': upload_daily,
        'processed': processed_daily,
        'error': error_daily,
        'image': image_daily,
        'pdf': pdf_daily,
        'dr_pdf': dr_pdf_daily,
        'glaucoma_pdf': glaucoma_pdf_daily
    }


def setup_environment():
    """Creates the necessary directories for the script to run."""
    print("Setting up the environment...")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSING_ERROR_DIR.mkdir(parents=True, exist_ok=True)

    # Get daily directories
    daily_dirs = get_daily_dirs()
    
    # Create all directories
    for dir_path in daily_dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)
    
    print("Directories are ready.")


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
def process_zip_file(zip_path: Path, session) -> tuple[list[str], str]:
    """
    Processes a single ZIP file, extracts metadata, and organizes files.
    Ensures the ZIP file is CLOSED before attempting to move it.
    
    Returns:
        tuple: (list_of_pdf_filenames, status_message)
        status_message can be:
        - "ok" for normal processing
        - "duplicate" for duplicate files
        - "error" for processing errors
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

    # Get daily directories for this processing run
    daily_dirs = get_daily_dirs()
    
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
        # Return empty list with duplicate status to indicate this was a duplicate file
        return ([], "duplicate")

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
            return ([], "skipped")
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
                _safe_move_local(zip_path, daily_dirs['error'] / zip_path.name)
            except PermissionError as pe:
                print(f"Final move failed for '{zip_path.name}' due to a lock: {pe}.")
            log_status(zip_path.name, "ERROR_BADZIP", "not a zip file")
            # Return empty list with error status to indicate this was an error
            return ([], "error")

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
            
            # Read metadata to get lab unit information
            lab_unit_id = None
            camera_id = None
            try:
                meta_dir = UPLOAD_DIR.parent / "upload_meta"
                meta_path = meta_dir / f"{zip_path.name}.json"
                if meta_path.exists():
                    import json
                    with open(meta_path, "r", encoding="utf-8") as mf:
                        meta = json.load(mf)
                        lab_unit_id = meta.get("lab_unit_id")
                        camera_id = meta.get("camera_id")
            except Exception:
                pass  # If metadata is not available or invalid, continue without lab_unit_id

            if not camera_id:
                raise ValueError("ZIP upload metadata is missing camera_id")

            camera = session.query(Camera).filter(
                Camera.id == camera_id,
                Camera.is_zip_upload_enabled.is_(True),
            ).first()
            if not camera:
                raise ValueError(f"Invalid ZIP-enabled camera_id in metadata: {camera_id}")
            
            new_patient_encounter = PatientEncounters(
                name=name,
                patient_id=patient_id,
                capture_date=capture_date,
                lab_unit_id=lab_unit_id,
            )
            # Populate proper Date column when possible
            parsed_dt = parse_capture_date(capture_date)
            if parsed_dt is not None:
                new_patient_encounter.capture_date_dt = parsed_dt
            new_zip_file.patient_encounter = new_patient_encounter

            print(f"  Identified Parent Directory: {dir_in_zip.name}")
            print(f"  Extracted Info -> Name: {name}, Patient ID: {patient_id}, Capture Date: {capture_date}")

            files_to_add = []
            files_to_add_pdfs = []
            # Filter files to only include those in the identified directory
            valid_files = [info for info in zf.infolist() 
                          if not info.is_dir() and info.filename.startswith(str(dir_in_zip)) and
                          not info.filename.startswith("__MACOSX/") and 
                          not Path(info.filename).name.startswith("._")]
            
            for member_info in valid_files:
                original_filepath = Path(member_info.filename)
                file_ext = original_filepath.suffix.lower()

                # New safe, UUID-based filename with preserved extension
                new_filename = f"{uuid4()}{file_ext}"

                # Determine destination directory and file type
                if file_ext in {'.jpg', '.jpeg'}:
                    dest_dir, file_type = daily_dirs['image'], 'image'
                elif file_ext == '.pdf':
                    dest_dir, file_type = daily_dirs['pdf'], 'pdf'
                else:
                    # Should not reach here due to pre-check, but keep defensive
                    continue

                target_path = dest_dir / new_filename
                
                # Extract file (intercept images for EXIF stripping)
                if file_ext in {'.jpg', '.jpeg'}:
                    try:
                        content = b""
                        with zf.open(member_info) as source:
                            content = source.read()
                            
                        # Strip EXIF
                        from utils.image_processing import strip_exif_data
                        clean_content = strip_exif_data(content)
                        
                        with open(target_path, "wb") as target:
                            target.write(clean_content)
                            
                        if len(clean_content) != len(content):
                            print(f"  - Stripped EXIF from {new_filename} ({len(content)}->{len(clean_content)} bytes)")
                    except Exception as e:
                        print(f"  - Failed to strip EXIF from {new_filename}: {e}. Saving original.")
                        # Fallback to direct copy
                        with zf.open(member_info) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        clean_content = content
                else:
                    # Direct stream copy for PDFs
                    with zf.open(member_info) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

                # Create appropriate model instance
                if file_type == 'pdf':
                    files_to_add_pdfs.append(EncounterFilePDF(filename=new_filename, file_type=file_type, uuid=str(uuid4()), lab_unit_id=lab_unit_id))
                    added_pdf_filenames.append(new_filename)
                else:
                    # Generate thumbnail for the image file
                    thumbnail_filename = None
                    try:
                        from utils.image_processing import generate_thumbnail, get_thumbnail_filename
                        from utils.fileUtils import get_upload_dirs

                        # Get the file path for the extracted image
                        image_path = daily_dirs['image'] / new_filename

                        if image_path.exists():
                            thumb_basename = get_thumbnail_filename(new_filename)
                            thumb_path = image_path.parent / thumb_basename

                            success = generate_thumbnail(image_path, thumb_path)
                            if success:
                                thumbnail_filename = thumb_basename
                                print(f"  - Generated thumbnail: {thumb_basename}")
                            else:
                                print(f"  - Failed to generate thumbnail for: {new_filename}")
                        else:
                            print(f"  - Image file not found for thumbnail generation: {image_path}")
                    except Exception as e:
                        print(f"  - Error generating thumbnail for {new_filename}: {e}")

                    metadata_result = None
                    try:
                        from utils.image_metadata import extract_image_metadata
                        metadata_result = extract_image_metadata(
                            image_bytes=content,
                            file_size_bytes=len(clean_content),
                        )
                    except Exception as e:
                        print(f"  - Failed to extract metadata for {new_filename}: {e}")

                    encounter_file = EncounterFile(
                        filename=new_filename,
                        file_type=file_type,
                        uuid=str(uuid4()),
                        lab_unit_id=lab_unit_id,
                        camera_id=camera_id,
                        thumbnail_filename=thumbnail_filename,
                    )
                    session.add(encounter_file)
                    session.flush()
                    files_to_add.append(encounter_file)

                    if metadata_result is not None:
                        try:
                            from utils.image_metadata import upsert_image_metadata
                            upsert_image_metadata(
                                session,
                                image_uuid=str(encounter_file.uuid),
                                image_variant="orig",
                                encounter_file_id=encounter_file.id,
                                metadata=metadata_result,
                            )
                        except Exception as e:
                            print(f"  - Failed to store metadata for {new_filename}: {e}")

                    try:
                        from utils.pii_detection_queue import enqueue_pii_detection_job, run_pii_detection_queue

                        enqueue_pii_detection_job(
                            session,
                            image_uuid=str(encounter_file.uuid),
                            image_variant="orig",
                            image_path=str(target_path),
                            source="auto",
                        )
                        run_pii_detection_queue(max_jobs=1)
                    except Exception as e:
                        print(f"  - Failed to enqueue PII detection for {new_filename}: {e}")
                print(f"  - Extracted and renamed '{original_filepath.name}' to '{new_filename}'")

            new_patient_encounter.encounter_files = files_to_add
            new_patient_encounter.encounter_file_pdfs = files_to_add_pdfs
        session.add(new_zip_file)

        # --- OUTSIDE the with-block: the ZIP file handle is closed now ---
        session.commit()
        success = True
        print(f"Successfully processed and logged '{zip_path.name}'.")
        return (added_pdf_filenames, "ok")

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
                safe_move(zip_path, daily_dirs['processed'] / zip_path.name)
                print(f"Moved '{zip_path.name}' to processed directory.")
                log_status(zip_path.name, "SUCCESS")
            else:
                safe_move(zip_path, daily_dirs['error'] / zip_path.name)
                print(f"Moved '{zip_path.name}' to error directory.")
                log_status(zip_path.name, "ERROR", error_message or "")
        except PermissionError as pe:
            # If it’s still locked by some external process, surface a clear message
            print(f"Final move failed for '{zip_path.name}' due to a lock: {pe}. "
                  f"Please close any apps using this file and rerun.")
            log_status(zip_path.name, "ERROR", f"PermissionError: {pe}")
        # Do not return here; allow previous return or raised exceptions to propagate


def ingest_zip_atomic(zip_path: Path, session: Session) -> tuple[list[int], list[int]]:
    """
    New Async Workflow Coordinator:
    1. Validates entire ZIP (All-or-Nothing).
    2. Extracts all files to local disk.
    3. Creates DB records (PatientEncounter, EncounterFile/PDF) in one transaction.
    4. Does NOT generate thumbnails or strip EXIF (delegated to async tasks).

    Returns:
        tuple(image_file_ids, pdf_file_ids) - lists of IDs for chained tasks.
    
    Raises:
        MaliciousZipError: If validation fails.
        Exception: For other errors.
    """
    
    # 1. Validation & Setup
    if not zipfile.is_zipfile(zip_path):
        raise MaliciousZipError("Not a valid ZIP file")

    daily_dirs = get_daily_dirs()
    md5_hash = calculate_md5(zip_path)
    
    # Check duplicate ZIP
    existing = session.query(ZipFile).filter_by(md5_hash=md5_hash).first()
    if existing:
        # Move to dup folder
        dup_dir = daily_dup_dir()
        try:
            shutil.move(str(zip_path), str(dup_dir / zip_path.name))
        except Exception:
            pass
        return [], []

    extracted_images = [] # (path, uuid, encounter_file_obj)
    extracted_pdfs = []   # (path, uuid, encounter_file_pdf_obj)
    
    # Get metadata for Lab Unit
    lab_unit_id = None
    camera_id = None
    try:
        meta_dir = UPLOAD_DIR.parent / "upload_meta"
        meta_path = meta_dir / f"{zip_path.name}.json"
        if meta_path.exists():
            import json
            with open(meta_path, "r", encoding="utf-8") as mf:
                meta = json.load(mf)
                lab_unit_id = meta.get("lab_unit_id")
                camera_id = meta.get("camera_id")
    except Exception:
        pass

    if not camera_id:
        raise ValueError("ZIP upload metadata is missing camera_id")

    camera = session.query(Camera).filter(
        Camera.id == camera_id,
        Camera.is_zip_upload_enabled.is_(True),
    ).first()
    if not camera:
        raise ValueError(f"Invalid ZIP-enabled camera_id in metadata: {camera_id}")

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # --- 1. Validate ALL entries first ---
            for info in zf.infolist():
                if info.is_dir(): continue
                inner_name = info.filename
                if inner_name.startswith("__MACOSX/") or Path(inner_name).name.startswith("._"):
                    continue
                
                # Path traversal check
                p = Path(inner_name)
                if inner_name.startswith("/") or any(part == ".." for part in p.parts):
                    raise MaliciousZipError(f"Path traversal detected: {inner_name}")
                
                # Extension check
                ext = p.suffix.lower()
                if ext not in ALLOWED_EXTS:
                    raise MaliciousZipError(f"Disallowed file extension: {inner_name}")
                
                # Magic bytes check
                detected = _sniff_member_type(zf, info)
                expected = 'pdf' if ext == '.pdf' else ('jpg' if ext in {'.jpg', '.jpeg'} else 'unknown')
                
                # Strict mismatch check
                if expected == 'pdf' and detected != 'pdf':
                    raise MaliciousZipError(f"Type mismatch (expected PDF): {inner_name}")
                if expected == 'jpg' and detected != 'jpg':
                    raise MaliciousZipError(f"Type mismatch (expected JPG): {inner_name}")

            # --- 2. Identify Directory Structure (Name_ID_Date) ---
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
                raise ValueError("No directory matching 'Name_ID_Date' format found.")

            # Parse Folder Name
            dir_parts = dir_in_zip.name.rstrip('/').split('_')
            capture_date = dir_parts[-1]
            patient_id = dir_parts[-2]
            name = ' '.join(dir_parts[:-2])
            
            # Create ZIP Record
            clean_name = clean_filename(zip_path.name)
            new_zip_file = ZipFile(zip_filename=clean_name, md5_hash=md5_hash)
            session.add(new_zip_file)
            
            # Create Patient Encounter
            new_patient_encounter = PatientEncounters(
                name=name,
                patient_id=patient_id,
                capture_date=capture_date,
                lab_unit_id=lab_unit_id,
            )
            parsed_dt = parse_capture_date(capture_date)
            if parsed_dt:
                new_patient_encounter.capture_date_dt = parsed_dt
            new_zip_file.patient_encounter = new_patient_encounter

            # --- 3. Extract & Create Objects ---
            valid_files = [info for info in zf.infolist() 
                          if not info.is_dir() and info.filename.startswith(str(dir_in_zip)) and
                          not info.filename.startswith("__MACOSX/") and 
                          not Path(info.filename).name.startswith("._")]

            files_to_add = []
            files_to_add_pdfs = []

            for member_info in valid_files:
                original_filepath = Path(member_info.filename)
                file_ext = original_filepath.suffix.lower()
                new_filename = f"{uuid4()}{file_ext}"
                file_uuid = str(uuid4())

                # Destinations
                if file_ext in {'.jpg', '.jpeg'}:
                    dest_dir = daily_dirs['image']
                    dest_dir.mkdir(parents=True, exist_ok=True) # Ensure dir exists
                    target_path = dest_dir / new_filename
                    
                    # Create DB Object
                    ef = EncounterFile(
                        filename=new_filename,
                        file_type='image',
                        uuid=file_uuid,
                        lab_unit_id=lab_unit_id,
                        camera_id=camera_id,
                        thumbnail_filename=None # Will be set by async task
                    )
                    files_to_add.append(ef)
                    extracted_images.append((target_path, ef))
                    
                elif file_ext == '.pdf':
                    dest_dir = daily_dirs['pdf']
                    dest_dir.mkdir(parents=True, exist_ok=True) # Ensure dir exists
                    target_path = dest_dir / new_filename
                    
                    # Create DB Object
                    ef_pdf = EncounterFilePDF(
                        filename=new_filename,
                        file_type='pdf',
                        uuid=file_uuid,
                        lab_unit_id=lab_unit_id
                    )
                    files_to_add_pdfs.append(ef_pdf)
                    extracted_pdfs.append((target_path, ef_pdf))

                # Extract File (Raw copy, no stripping yet)
                with zf.open(member_info) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)
            
            # Link to Encounter
            new_patient_encounter.encounter_files = files_to_add
            new_patient_encounter.encounter_file_pdfs = files_to_add_pdfs
            
            # Commit Transaction
            session.commit()
            
            # Move ZIP to processed
            try:
                shutil.move(str(zip_path), str(daily_dirs['processed'] / zip_path.name))
            except Exception:
                pass # Non-critical if move fails
            
            # Return IDs for async processing
            return ([f.id for f in files_to_add], [f.id for f in files_to_add_pdfs])

    except Exception:
        session.rollback()
        # Move to error
        try:
            shutil.move(str(zip_path), str(daily_dirs['error'] / zip_path.name))
        except Exception:
            pass
        raise


# --- Main Execution ---

def main():
    """Main function to run the entire workflow."""
    print("Starting ZIP file processing workflow...")
    setup_environment()

    session = Session()

    # Get daily upload directory
    daily_dirs = get_daily_dirs()
    
    # Filter out macOS resource fork artifacts like '._*.zip'
    zip_files = [p for p in daily_dirs['upload'].glob("*.zip") if not p.name.startswith("._")]
    if not zip_files:
        print("\nNo new ZIP files found in 'files/uploaded'.")
    else:
        for zip_path in zip_files:
            process_zip_file(zip_path, session)

    session.close()
    print("\nWorkflow finished.")


if __name__ == "__main__":
    main()
