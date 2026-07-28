#main.py
import os
import json
import zipfile
import hashlib
import re
import shutil
import logging
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
    EncounterSetImage,
    EncounterSetAttachment,
    JobItem,
    Camera,
    Session,
    BASE_DIR, 
    UPLOAD_DIR,
    IMAGE_DIR,
    PDF_DIR,
    PROCESSED_DIR,
    PROCESSING_ERROR_DIR,
)
from upload_profiles.models import PatientEncounterTargetDisease
from auth.utils import utcnow
from utils.image_processing import generate_thumbnail, get_thumbnail_filename, strip_exif_data
from utils.log_sanitize import sanitize_log_value
from uuid import uuid4

# Path for log file
LOG_FILE = BASE_DIR / os.getenv("ZIP_INGEST_LOG", "logs/zip_main_process_log.txt")
MALICIOUS_LOG_FILE = BASE_DIR / os.getenv("MALICIOUS_UPLOAD_LOG", "logs/malicious_uploads.log")
logger = logging.getLogger(__name__)

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


def _load_zip_upload_context(zip_path: Path, upload_context: dict | None = None) -> dict:
    """Resolve durable upload scope for a ZIP, falling back to legacy sidecar metadata."""
    context = dict(upload_context or {})
    meta_path = UPLOAD_DIR.parent / "upload_meta" / f"{zip_path.name}.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as mf:
            sidecar_context = json.load(mf)
        context = {**sidecar_context, **{key: value for key, value in context.items() if value is not None}}

    ingest_mode = context.get("ingest_mode")
    required = ("lab_unit_id", "project_id", "default_disease_id")
    if ingest_mode != "encounter_set":
        required = (*required, "camera_id")
    missing = [name for name in required if not context.get(name)]
    if missing:
        raise ValueError(f"ZIP upload metadata is missing required scope: {', '.join(missing)}")

    normalized = dict(context)
    for key in ("lab_unit_id", "project_id", "camera_id", "default_disease_id", "upload_profile_id"):
        value = context.get(key)
        normalized[key] = int(value) if value is not None else None
    return normalized


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


ACTIVE_JOB_ITEM_STATES = {"queued", "processing", "running", "started"}


def _processed_cleanup_destination(zip_path: Path) -> Path:
    """Return a non-overwriting processed archive destination for an intake ZIP."""
    destination_dir = PROCESSED_DIR / zip_path.parent.name
    destination = destination_dir / zip_path.name
    if not destination.exists():
        return destination

    for index in range(1, 10_000):
        candidate = destination_dir / f"{zip_path.stem}.cleanup-{index}{zip_path.suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No available processed destination for {zip_path.name}")


def _iter_zip_intake_files(date_folder: str | None = None) -> list[Path]:
    if date_folder:
        date_path = Path(date_folder)
        if date_path.name != date_folder or date_path.is_absolute():
            raise ValueError("date_folder must be a single intake folder name")
        search_roots = [UPLOAD_DIR / date_folder]
    else:
        search_roots = [UPLOAD_DIR]

    zip_paths: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        zip_paths.extend(
            path
            for path in root.rglob("*.zip")
            if path.is_file() and not path.name.startswith("._")
        )
    return sorted(zip_paths)


def _zip_intake_file_cleanup_status(session, zip_path: Path) -> tuple[bool, str, ZipFile | None]:
    db_filename = clean_filename(zip_path.name)
    zip_file = session.query(ZipFile).filter(ZipFile.zip_filename == db_filename).one_or_none()
    if zip_file is None:
        return False, "missing_zip_file_row", None

    encounter = zip_file.patient_encounter
    if encounter is None:
        return False, "missing_patient_encounter", zip_file

    if (
        not encounter.encounter_files
        and not encounter.encounter_file_pdfs
        and not encounter.encounter_set_images
        and not encounter.encounter_set_attachments
    ):
        return False, "missing_extracted_encounter_file", zip_file

    active_job_item = (
        session.query(JobItem.id)
        .filter(JobItem.filename.in_({zip_path.name, db_filename}))
        .filter(JobItem.state.in_(ACTIVE_JOB_ITEM_STATES))
        .first()
    )
    if active_job_item is not None:
        return False, "active_job_item_exists", zip_file

    return True, "eligible", zip_file


def cleanup_processed_zip_intake_files(
    session,
    *,
    date_folder: str | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict:
    """
    Move stale intake ZIP files to processed only after confirming ingestion in DB.

    A ZIP is eligible only when it has a zip_files row, linked encounter, at
    least one extracted image/PDF row, and no active job item for that ZIP.
    """
    zip_paths = _iter_zip_intake_files(date_folder)
    if limit is not None:
        zip_paths = zip_paths[: max(limit, 0)]

    result = {
        "dry_run": dry_run,
        "date_folder": date_folder,
        "scanned": 0,
        "eligible": 0,
        "moved": 0,
        "skipped": 0,
        "errors": 0,
        "items": [],
    }

    for zip_path in zip_paths:
        result["scanned"] += 1
        item = {
            "filename": zip_path.name,
            "source": str(zip_path.relative_to(UPLOAD_DIR.parent)),
            "status": "skipped",
            "reason": None,
            "destination": None,
        }
        try:
            is_eligible, reason, zip_file = _zip_intake_file_cleanup_status(session, zip_path)
            item["reason"] = reason
            if not is_eligible:
                result["skipped"] += 1
                result["items"].append(item)
                continue

            result["eligible"] += 1
            destination = _processed_cleanup_destination(zip_path)
            item["destination"] = str(destination.relative_to(PROCESSED_DIR.parent))
            if dry_run:
                item["status"] = "eligible"
                result["items"].append(item)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(zip_path), str(destination))
            item["status"] = "moved"
            result["moved"] += 1
            logger.info(
                "Moved processed intake ZIP %s to %s after DB confirmation zip_file_id=%s",
                sanitize_log_value(zip_path.name),
                sanitize_log_value(destination),
                getattr(zip_file, "id", None),
            )
        except Exception as exc:
            result["errors"] += 1
            item["status"] = "error"
            item["reason"] = type(exc).__name__
            item["error"] = str(exc)
            logger.error(
                "Failed cleanup check/move for intake ZIP %s: %s",
                sanitize_log_value(zip_path),
                sanitize_log_value(exc),
                exc_info=True,
            )
        result["items"].append(item)

    return result


# --- Main Processing Logic ---
def process_zip_file(zip_path: Path, session, upload_context: dict | None = None) -> tuple[list[str], str]:
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
    if (upload_context or {}).get("ingest_mode") == "encounter_set":
        if (upload_context or {}).get("encounter_set_zip_format") == "iitk":
            from encounter_sets.iitk_encounterset_zip_importer import ingest_iitk_encounterset_zip

            ingest_iitk_encounterset_zip(zip_path, session, upload_context=upload_context)
        else:
            ingest_remidio_zip_as_encounter_set(zip_path, session, upload_context=upload_context)
        return ([], "ok")

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
            
            context = _load_zip_upload_context(zip_path, upload_context)
            lab_unit_id = context["lab_unit_id"]
            camera_id = context["camera_id"]
            project_id = context["project_id"]
            default_disease_id = context["default_disease_id"]
            upload_profile_id = context.get("upload_profile_id")

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
                project_id=project_id,
                disease_id=default_disease_id,
                upload_profile_id=upload_profile_id,
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
                    files_to_add_pdfs.append(
                        EncounterFilePDF(
                            filename=new_filename,
                            file_type=file_type,
                            uuid=str(uuid4()),
                            lab_unit_id=lab_unit_id,
                            project_id=project_id,
                        )
                    )
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
                        project_id=project_id,
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


def ingest_zip_atomic(zip_path: Path, session: Session, upload_context: dict | None = None) -> tuple[list[int], list[int]]:
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
    if (upload_context or {}).get("ingest_mode") == "encounter_set":
        if (upload_context or {}).get("encounter_set_zip_format") == "iitk":
            from encounter_sets.iitk_encounterset_zip_importer import ingest_iitk_encounterset_zip

            summary = ingest_iitk_encounterset_zip(zip_path, session, upload_context=upload_context)
        else:
            summary = ingest_remidio_zip_as_encounter_set(zip_path, session, upload_context=upload_context)
        return summary["encounter_set_image_ids"], summary["encounter_set_attachment_ids"]

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
    
    context = _load_zip_upload_context(zip_path, upload_context)
    lab_unit_id = context["lab_unit_id"]
    camera_id = context["camera_id"]
    project_id = context["project_id"]
    default_disease_id = context["default_disease_id"]
    upload_profile_id = context.get("upload_profile_id")

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
                project_id=project_id,
                disease_id=default_disease_id,
                upload_profile_id=upload_profile_id,
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
                        project_id=project_id,
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
                        lab_unit_id=lab_unit_id,
                        project_id=project_id,
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
                daily_dirs['processed'].mkdir(parents=True, exist_ok=True)
                shutil.move(str(zip_path), str(daily_dirs['processed'] / zip_path.name))
            except Exception as exc:
                logger.warning(
                    "Failed to move processed ZIP %s to %s: %s",
                    sanitize_log_value(zip_path.name),
                    sanitize_log_value(daily_dirs['processed'] / zip_path.name),
                    sanitize_log_value(exc),
                    exc_info=True,
                )
                log_status(zip_path.name, "MOVE_FAILED", str(exc))
            
            # Return IDs for async processing
            return ([f.id for f in files_to_add], [f.id for f in files_to_add_pdfs])

    except Exception:
        session.rollback()
        # Move to error
        try:
            daily_dirs['error'].mkdir(parents=True, exist_ok=True)
            shutil.move(str(zip_path), str(daily_dirs['error'] / zip_path.name))
        except Exception as exc:
            logger.error(
                "Failed to move errored ZIP %s to %s: %s",
                sanitize_log_value(zip_path.name),
                sanitize_log_value(daily_dirs['error'] / zip_path.name),
                sanitize_log_value(exc),
                exc_info=True,
            )
            log_status(zip_path.name, "ERROR_MOVE_FAILED", str(exc))
        raise


def ingest_remidio_zip_as_encounter_set(zip_path: Path, session: Session, upload_context: dict | None = None) -> dict:
    """
    Ingest a Remidio ZIP as an EncounterSet.

    Current ZIP contracts:
    - patient folder name is <patient_name>_<mrn>_<capture_date>
    - FOP clinical images live under a fop/ path segment
    - PRISTINE clinical images live directly under the patient folder
    - PDFs are report/document attachments, never grading-task evidence
    """
    if not zipfile.is_zipfile(zip_path):
        raise MaliciousZipError("Not a valid ZIP file")

    daily_dirs = get_daily_dirs()
    md5_hash = calculate_md5(zip_path)
    existing = session.query(ZipFile).filter_by(md5_hash=md5_hash).first()
    if existing:
        dup_dir = daily_dup_dir()
        try:
            shutil.move(str(zip_path), str(dup_dir / zip_path.name))
        except Exception:
            pass
        return {
            "patient_encounter_id": None,
            "encounter_set_image_ids": [],
            "encounter_set_attachment_ids": [],
            "status": "duplicate",
        }

    context = _load_zip_upload_context(zip_path, upload_context)
    lab_unit_id = context["lab_unit_id"]
    project_id = context["project_id"]
    upload_profile_id = context.get("upload_profile_id")
    target_disease_ids = [int(value) for value in context.get("target_disease_ids") or []]

    image_ids: list[int] = []
    attachment_ids: list[int] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = _validated_remidio_zip_members(zf)
            patient_dir = _patient_folder_from_members(members)
            patient_name, patient_id, capture_date = _parse_patient_folder(patient_dir.name)
            image_members = [info for info in members if Path(info.filename).suffix.lower() in {".jpg", ".jpeg"}]
            pdf_members = [info for info in members if Path(info.filename).suffix.lower() == ".pdf"]
            camera_type, camera_flags = _infer_camera_type(patient_dir, image_members)
            pdf_types = [_classify_pdf_member(info, fallback_camera_type=camera_type) for info in pdf_members]

            zip_file = ZipFile(zip_filename=clean_filename(zip_path.name), md5_hash=md5_hash)
            session.add(zip_file)
            encounter = PatientEncounters(
                name=patient_name,
                patient_id=patient_id,
                capture_date=capture_date,
                capture_date_dt=parse_capture_date(capture_date),
                lab_unit_id=lab_unit_id,
                project_id=project_id,
                upload_profile_id=upload_profile_id,
                disease_id=target_disease_ids[0] if len(target_disease_ids) == 1 else None,
                is_set_based=True,
                metadata_json={
                    "source_kind": "remidio_zip",
                    "source_identity": "zip_folder_name",
                    "source_zip_filename": zip_path.name,
                    "source_patient_folder": str(patient_dir),
                    "camera_type": camera_type,
                    "camera_inference": camera_flags,
                    "report_types": sorted({item for item in pdf_types if item}),
                    "age": None,
                    "gender": None,
                },
            )
            zip_file.patient_encounter = encounter
            session.flush()

            for disease_id in target_disease_ids:
                session.add(
                    PatientEncounterTargetDisease(
                        patient_encounter_id=encounter.id,
                        disease_id=disease_id,
                        is_default=False,
                    )
                )

            folder_rel = f"files/encounter_sets/{utcnow().strftime('%Y_%m_%d')}/{encounter.id}"
            image_dir = BASE_DIR / folder_rel
            image_dir.mkdir(parents=True, exist_ok=True)
            for position, member_info in enumerate(image_members, start=1):
                source_path = Path(member_info.filename)
                ext = source_path.suffix.lower()
                stored_filename = f"{uuid4()}{ext}"
                target_path = image_dir / stored_filename
                with zf.open(member_info) as source:
                    content = source.read()
                safe_content = strip_exif_data(content)
                target_path.write_bytes(safe_content)
                thumbnail_filename = _generate_encounter_set_zip_thumbnail(target_path, stored_filename)
                image_camera_type = _camera_type_for_image(patient_dir, member_info)
                image = EncounterSetImage(
                    uuid=str(uuid4()),
                    patient_encounter_id=encounter.id,
                    spatial_position=position,
                    original_filename=stored_filename,
                    folder_rel=folder_rel,
                    file_hash=hashlib.md5(safe_content).hexdigest(),
                    asset_kind="clinical_image",
                    creates_task=True,
                    is_pii=False,
                    visible_to_grader=True,
                    project_id=project_id,
                    camera_id=context.get("camera_id"),
                    hospital_id=context.get("hospital_id"),
                    thumbnail_filename=thumbnail_filename,
                    metadata_json={
                        "source_kind": "remidio_zip",
                        "source_zip_filename": zip_path.name,
                        "source_path": str(source_path),
                        "source_folder": str(source_path.parent),
                        "camera_type": image_camera_type,
                    },
                    created_at=utcnow(),
                )
                session.add(image)
                session.flush()
                image_ids.append(image.id)

            attachment_dir_rel = f"{folder_rel}/attachments"
            attachment_dir = BASE_DIR / attachment_dir_rel
            attachment_dir.mkdir(parents=True, exist_ok=True)
            for member_info, report_type in zip(pdf_members, pdf_types):
                source_path = Path(member_info.filename)
                stored_filename = f"{uuid4()}.pdf"
                target_path = attachment_dir / stored_filename
                with zf.open(member_info) as source:
                    content = source.read()
                target_path.write_bytes(content)
                attachment = EncounterSetAttachment(
                    patient_encounter_id=encounter.id,
                    uuid=str(uuid4()),
                    asset_kind="pdf",
                    original_filename=source_path.name,
                    stored_filename=stored_filename,
                    folder_rel=attachment_dir_rel,
                    mime_type="application/pdf",
                    file_size_bytes=len(content),
                    file_hash=hashlib.md5(content).hexdigest(),
                    is_pii=True,
                    visible_to_grader=False,
                    creates_task=False,
                    project_id=project_id,
                    upload_profile_id=upload_profile_id,
                    hospital_id=context.get("hospital_id"),
                    metadata_json={
                        "source_kind": "remidio_zip",
                        "source_zip_filename": zip_path.name,
                        "source_path": str(source_path),
                        "report_type": report_type,
                        "camera_type": camera_type,
                    },
                    created_at=utcnow(),
                )
                session.add(attachment)
                session.flush()
                attachment_ids.append(attachment.id)

            if not image_ids:
                raise ValueError("Remidio EncounterSet ZIP contains no clinical JPG/JPEG images.")

            session.commit()
            daily_dirs["processed"].mkdir(parents=True, exist_ok=True)
            shutil.move(str(zip_path), str(daily_dirs["processed"] / zip_path.name))
            try:
                log_status(zip_path.name, "SUCCESS_ENCOUNTER_SET")
            except OSError as exc:
                logger.warning("Could not write ZIP EncounterSet ingest log for %s: %s", sanitize_log_value(zip_path.name), sanitize_log_value(exc))
            return {
                "patient_encounter_id": encounter.id,
                "encounter_set_image_ids": image_ids,
                "encounter_set_attachment_ids": attachment_ids,
                "status": "ok",
            }
    except Exception:
        session.rollback()
        try:
            daily_dirs["error"].mkdir(parents=True, exist_ok=True)
            shutil.move(str(zip_path), str(daily_dirs["error"] / zip_path.name))
        except Exception as exc:
            logger.error(
                "Failed to move errored EncounterSet ZIP %s: %s",
                sanitize_log_value(zip_path.name),
                sanitize_log_value(exc),
                exc_info=True,
            )
        raise


def _validated_remidio_zip_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        inner_name = info.filename
        if inner_name.startswith("__MACOSX/") or Path(inner_name).name.startswith("._"):
            continue
        path = Path(inner_name)
        if inner_name.startswith("/") or any(part == ".." for part in path.parts):
            raise MaliciousZipError(f"Path traversal detected: {inner_name}")
        ext = path.suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise MaliciousZipError(f"Disallowed file extension: {inner_name}")
        detected = _sniff_member_type(zf, info)
        if ext == ".pdf" and detected != "pdf":
            raise MaliciousZipError(f"Type mismatch (expected PDF): {inner_name}")
        if ext in {".jpg", ".jpeg"} and detected != "jpg":
            raise MaliciousZipError(f"Type mismatch (expected JPG): {inner_name}")
        members.append(info)
    return members


def _patient_folder_from_members(members: list[zipfile.ZipInfo]) -> Path:
    for info in members:
        parts = Path(info.filename).parts
        for index, part in enumerate(parts[:-1]):
            if len(part.split("_")) >= 3:
                return Path(*parts[: index + 1])
    raise ValueError("No directory matching the 'Name_ID_Date' format found.")


def _parse_patient_folder(folder_name: str) -> tuple[str, str, str]:
    parts = [part for part in folder_name.rstrip("/").split("_") if part]
    if len(parts) < 3:
        raise ValueError("Patient folder must match '<patient_name>_<mrn>_<capture_date>'.")
    capture_date = parts[-1]
    patient_id = parts[-2]
    patient_name = " ".join(parts[:-2]).strip()
    if not patient_name or not patient_id or not capture_date:
        raise ValueError("Patient folder is missing patient name, MRN, or capture date.")
    return patient_name, patient_id, capture_date


def _infer_camera_type(patient_dir: Path, image_members: list[zipfile.ZipInfo]) -> tuple[str, dict]:
    has_fop = False
    has_direct = False
    for info in image_members:
        rel_parts = _relative_parts_under_patient(patient_dir, Path(info.filename))
        if any(part.lower() == "fop" for part in rel_parts[:-1]):
            has_fop = True
        elif len(rel_parts) == 1:
            has_direct = True
    if has_fop and has_direct:
        return "mixed", {"has_fop_folder_images": True, "has_direct_patient_folder_images": True, "needs_review": True}
    if has_fop:
        return "FOP", {"has_fop_folder_images": True, "has_direct_patient_folder_images": False}
    if has_direct:
        return "PRISTINE", {"has_fop_folder_images": False, "has_direct_patient_folder_images": True}
    return "unknown", {"has_fop_folder_images": False, "has_direct_patient_folder_images": False, "needs_review": True}


def _camera_type_for_image(patient_dir: Path, info: zipfile.ZipInfo) -> str:
    rel_parts = _relative_parts_under_patient(patient_dir, Path(info.filename))
    if any(part.lower() == "fop" for part in rel_parts[:-1]):
        return "FOP"
    if len(rel_parts) == 1:
        return "PRISTINE"
    return "unknown"


def _relative_parts_under_patient(patient_dir: Path, source_path: Path) -> tuple[str, ...]:
    parts = source_path.parts
    patient_parts = patient_dir.parts
    for index in range(0, len(parts) - len(patient_parts) + 1):
        if parts[index : index + len(patient_parts)] == patient_parts:
            return parts[index + len(patient_parts) :]
    return parts


def _classify_pdf_member(info: zipfile.ZipInfo, *, fallback_camera_type: str) -> str:
    text = " ".join(Path(info.filename).parts).lower()
    if "glaucoma" in text or "gma" in text:
        return "fop_glaucoma_report"
    if "diabetic" in text or "retinopathy" in text or re.search(r"(^|[^a-z0-9])dr([^a-z0-9]|$)", text):
        return "fop_dr_report"
    if "pristine" in text or fallback_camera_type == "PRISTINE":
        return "pristine_report"
    if fallback_camera_type == "FOP":
        return "fop_report"
    return "unknown_report"


def _generate_encounter_set_zip_thumbnail(image_path: Path, filename: str) -> str | None:
    try:
        thumbnail_filename = get_thumbnail_filename(filename)
        thumbnail_dir = image_path.parent / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        if generate_thumbnail(image_path, thumbnail_dir / thumbnail_filename):
            return thumbnail_filename
    except Exception as exc:
        logger.info("EncounterSet ZIP thumbnail generation failed: %s", sanitize_log_value(exc))
    return None


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
