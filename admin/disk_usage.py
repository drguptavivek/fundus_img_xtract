"""Admin disk usage assessment routes."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

from flask import current_app, render_template, request, jsonify, flash, redirect, url_for

from auth.roles import roles_required
from models import EncounterFile, EncounterFilePDF, JobItem, PatientEncounters, ZipFile
from db_transaction_manager import get_db_session
from utils.log_sanitize import sanitize_log_value
from zip_processor import clean_filename

ACTIVE_JOB_ITEM_STATES = {"queued", "processing", "running", "started"}
ZIP_ARCHIVE_DB_CHECK_BATCH_SIZE = 500

@roles_required('admin')
def _get_directories_to_analyze() -> List[Path]:
    """Return the base directories to analyze (files and logs)."""
    directories = []
    
    # Get files directory
    configured_files = current_app.config.get("FILES_ROOT")
    if configured_files:
        files_root = Path(configured_files)
    else:
        # files directory is in the same directory as app.py (current workspace)
        files_root = Path(current_app.root_path) / "files"
    
    # Check if files directory exists and add to list
    if files_root.exists():
        directories.append(files_root.resolve())
        current_app.logger.info(
            "Files directory found: %s",
            sanitize_log_value(files_root.resolve()),
        )
    else:
        current_app.logger.warning(
            "Files directory not found at: %s",
            sanitize_log_value(files_root.resolve()),
        )
    
    # Get logs directory
    configured_logs = current_app.config.get("LOG_VIEWER_ROOT")
    if configured_logs:
        logs_root = Path(configured_logs)
    else:
        logs_root = Path(current_app.root_path) / "logs"
    
    # Check if logs directory exists and add to list
    if logs_root.exists():
        directories.append(logs_root.resolve())
        current_app.logger.info(
            "Logs directory found: %s",
            sanitize_log_value(logs_root.resolve()),
        )
    else:
        current_app.logger.warning(
            "Logs directory not found at: %s",
            sanitize_log_value(logs_root.resolve()),
        )
    
    return directories


def _get_directory_size(path: Path) -> int:
    """Calculate the total size of a directory recursively (files only).
    
    Returns:
        Total size in bytes
    """
    total_size = 0
    
    if not path.exists() or not path.is_dir():
        return 0
    
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total_size += entry.stat().st_size
                except (OSError, PermissionError):
                    # Skip files that can't be accessed
                    continue
    except (OSError, PermissionError):
        # Skip directories that can't be accessed
        pass
    
    return total_size


def _count_directories(path: Path) -> int:
    """Count the number of subdirectories in a directory recursively.
    
    Returns:
        Number of subdirectories
    """
    count = 0
    
    if not path.exists() or not path.is_dir():
        return 0
    
    try:
        for entry in path.rglob("*"):
            if entry.is_dir():
                count += 1
    except (OSError, PermissionError):
        # Skip directories that can't be accessed
        pass
    
    return count


def _collect_directory_stats(path: Path) -> Dict[Path, Dict[str, int | bool]]:
    """Collect recursive directory size/count information in one tree walk."""
    stats: Dict[Path, Dict[str, int | bool]] = {}

    def walk(directory: Path) -> tuple[int, int, bool]:
        size_bytes = 0
        dir_count = 0
        has_subdirs = False

        try:
            entries = list(directory.iterdir())
        except (OSError, PermissionError):
            stats[directory.resolve()] = {
                "size_bytes": 0,
                "dir_count": 0,
                "has_subdirs": False,
            }
            return 0, 0, False

        for entry in entries:
            try:
                if entry.is_dir():
                    has_subdirs = True
                    child_size, child_dir_count, _ = walk(entry)
                    size_bytes += child_size
                    dir_count += child_dir_count + 1
                elif entry.is_file():
                    size_bytes += entry.stat().st_size
            except (OSError, PermissionError):
                continue

        stats[directory.resolve()] = {
            "size_bytes": size_bytes,
            "dir_count": dir_count,
            "has_subdirs": has_subdirs,
        }
        return size_bytes, dir_count, has_subdirs

    if path.exists() and path.is_dir():
        walk(path)

    return stats


def _directory_stat(
    directory_stats: Dict[Path, Dict[str, int | bool]],
    path: Path,
    key: str,
    default,
):
    return directory_stats.get(path.resolve(), {}).get(key, default)


@roles_required('admin')
def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable format."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.2f} {size_names[i]}"

@roles_required('admin')
def _analyze_directory(
    path: Path,
    parent_path: Path = None,
    level: int = 0,
    expanded_dirs: set = None,
    directory_stats: Dict[Path, Dict[str, int | bool]] | None = None,
) -> List[Dict]:
    """Analyze a directory and return information about its subdirectories recursively.
    
    Args:
        path: The directory path to analyze
        parent_path: The parent directory path for calculating relative paths
        level: Current depth level in the tree
        expanded_dirs: Set of directory paths that should be expanded
        
    Returns:
        List of dictionaries containing directory information
    """
    if not path.exists() or not path.is_dir():
        return []
    
    if expanded_dirs is None:
        expanded_dirs = set()
    if directory_stats is None:
        directory_stats = _collect_directory_stats(path)
    
    if parent_path is None:
        parent_path = path.parent
    
    directories = []
    
    try:
        for entry in sorted(path.iterdir()):
            if entry.is_dir():
                try:
                    size_bytes = int(_directory_stat(directory_stats, entry, "size_bytes", 0))
                    dir_count = int(_directory_stat(directory_stats, entry, "dir_count", 0))
                    has_subdirs = bool(_directory_stat(directory_stats, entry, "has_subdirs", False))
                    stat = entry.stat()
                    
                    # Create a unique identifier for this directory
                    dir_id = str(entry.relative_to(parent_path))
                    
                    dir_info = {
                        "name": entry.name,
                        "path": str(entry.relative_to(parent_path)),
                        "level": level,
                        "size_bytes": size_bytes,
                        "size_formatted": _format_size(size_bytes),
                        "dir_count": dir_count,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        "has_subdirs": has_subdirs,
                        "expanded": dir_id in expanded_dirs,
                        "usage_percentage": 0,  # Will be calculated later
                    }
                    
                    # Recursively analyze subdirectories if this directory is expanded
                    if dir_info["expanded"] and dir_info["has_subdirs"]:
                        dir_info["subdirectories"] = _analyze_directory(
                            entry,
                            parent_path,
                            level + 1,
                            expanded_dirs,
                            directory_stats,
                        )
                    else:
                        dir_info["subdirectories"] = []
                    
                    directories.append(dir_info)
                    
                except (OSError, PermissionError):
                    # Skip directories that can't be accessed
                    continue
                    
    except (OSError, PermissionError):
        # Skip if the parent directory can't be accessed
        pass
    
    return directories


@roles_required("admin")
def disk_usage():
    """Render the disk usage analysis page for the files and logs directories."""
    directories_to_analyze = _get_directories_to_analyze()
    current_app.logger.info(
        "Directories to analyze: %s",
        sanitize_log_value([str(d) for d in directories_to_analyze]),
    )
    
    # Get the list of expanded directories from request args
    expanded_param = request.args.get("expanded", "")
    expanded_dirs = set(expanded_param.split(",")) if expanded_param else set()
    
    # Handle toggle action
    toggle_dir = request.args.get("toggle")
    if toggle_dir:
        if toggle_dir in expanded_dirs:
            expanded_dirs.remove(toggle_dir)
        else:
            expanded_dirs.add(toggle_dir)
    
    all_directories = []
    total_size = 0
    total_files = 0
    
    files_root = None

    # Analyze each base directory
    for base_dir in directories_to_analyze:
        current_app.logger.info(
            "Analyzing directory: %s",
            sanitize_log_value(base_dir),
        )
        if base_dir.exists():
            if base_dir.name == "files":
                files_root = base_dir

            directory_stats = _collect_directory_stats(base_dir)
            dir_size = int(_directory_stat(directory_stats, base_dir, "size_bytes", 0))
            dir_count = int(_directory_stat(directory_stats, base_dir, "dir_count", 0))
            has_subdirs = bool(_directory_stat(directory_stats, base_dir, "has_subdirs", False))
            total_size += dir_size
            total_files += dir_count  # Reusing this field for directory count
            
            # Create an entry for the base directory itself
            stat = base_dir.stat()
            base_dir_info = {
                "name": base_dir.name,
                "path": base_dir.name,
                "level": 0,
                "size_bytes": dir_size,
                "size_formatted": _format_size(dir_size),
                "dir_count": dir_count,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                "is_base_directory": True,
                "has_subdirs": has_subdirs,
                "expanded": base_dir.name in expanded_dirs,
            }
            
            # Get subdirectories recursively
            base_dir_info["subdirectories"] = _analyze_directory(
                base_dir,
                base_dir.parent,
                1,
                expanded_dirs,
                directory_stats,
            )
            
            all_directories.append(base_dir_info)
            current_app.logger.info(
                "Added directory to results: %s (%s)",
                sanitize_log_value(base_dir.name),
                sanitize_log_value(base_dir_info['size_formatted']),
            )
        else:
            current_app.logger.warning(
                "Directory does not exist: %s",
                sanitize_log_value(base_dir),
            )
    
    current_app.logger.info(
        "Total directories found: %s",
        sanitize_log_value(len(all_directories)),
    )
    
    # Calculate disk usage percentage for each directory
    def calculate_percentages(dirs, parent_size=None):
        for directory in dirs:
            if parent_size is not None and parent_size > 0:
                directory["usage_percentage"] = (directory["size_bytes"] / parent_size) * 100
            elif total_size > 0:
                directory["usage_percentage"] = (directory["size_bytes"] / total_size) * 100
            else:
                directory["usage_percentage"] = 0
            
            # Recursively calculate for subdirectories
            if directory.get("subdirectories"):
                calculate_percentages(directory["subdirectories"], directory["size_bytes"])
    
    calculate_percentages(all_directories)
    
    # Sort base directories by size (largest first)
    all_directories.sort(key=lambda x: x["size_bytes"], reverse=True)
    
    # Check if any dupmd5 directory exists
    def has_dupmd5_directory(directories):
        for directory in directories:
            if directory["name"].startswith("dupmd5_"):
                return True
            if directory.get("subdirectories") and has_dupmd5_directory(directory["subdirectories"]):
                return True
        return False
    
    # Also check for dupmd5 directories at the files root level
    def has_dupmd5_at_root():
        try:
            files_root = Path(current_app.root_path) / "files"
            if files_root.exists():
                for item in files_root.iterdir():
                    if item.is_dir() and item.name.startswith("dupmd5_"):
                        return True
        except Exception as e:
            current_app.logger.warning("Failed to check for dupmd5 at root: %s", sanitize_log_value(e))
        return False
    
    has_dupmd5 = has_dupmd5_directory(all_directories) or has_dupmd5_at_root()
    
    # Check if there are old processed ZIP files (older than 1 month)
    def has_old_processed_zips_on_disk(processed_dir: Path) -> bool:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not processed_dir.exists():
            return False
        try:
            date_dirs = [entry for entry in processed_dir.iterdir() if entry.is_dir()]
        except (OSError, PermissionError) as exc:
            current_app.logger.warning(
                "Failed to check processed ZIP archive dates under %s: %s",
                sanitize_log_value(processed_dir),
                sanitize_log_value(exc),
            )
            return False

        for date_dir in date_dirs:
            try:
                dir_date = datetime.strptime(date_dir.name, "%Y_%m_%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if dir_date < cutoff_date:
                return True
        return False
    
    processed_zip_dir = (files_root or Path(current_app.root_path) / "files") / "zips_upload_processed"
    has_old_zips = has_old_processed_zips_on_disk(processed_zip_dir)
    
    context = {
        "total_size_bytes": total_size,
        "total_size_formatted": _format_size(total_size),
        "total_files": total_files,  # This is now total directory count
        "directories": all_directories,
        "expanded_dirs": ",".join(expanded_dirs),
        "has_dupmd5": has_dupmd5,
        "has_old_zips": has_old_zips,
    }
    
    return render_template("admin/disk_usage.html", **context)


@roles_required("admin")
def delete_duplicates():
    """Delete duplicate files from dupmd5 directories."""
    if request.method == "POST":
        try:
            files_root = Path(current_app.root_path) / "files"
            
            # Find all dupmd5 directories
            dupmd5_dirs = []
            for item in files_root.iterdir():
                if item.is_dir() and item.name.startswith("dupmd5_"):
                    dupmd5_dirs.append(item)
            
            deleted_count = 0
            deleted_size = 0
            
            for dupmd5_dir in dupmd5_dirs:
                current_app.logger.info(
                    "Processing duplicate directory: %s",
                    sanitize_log_value(dupmd5_dir),
                )
                
                for file_path in dupmd5_dir.iterdir():
                    if file_path.is_file():
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            deleted_count += 1
                            deleted_size += file_size
                            current_app.logger.info(
                                "Deleted duplicate file: %s",
                                sanitize_log_value(file_path.name),
                            )
                        except (OSError, PermissionError) as e:
                            current_app.logger.error(
                                "Failed to delete %s: %s",
                                sanitize_log_value(file_path),
                                sanitize_log_value(e),
                            )
                
                # Try to remove the directory if it's empty
                try:
                    if not any(dupmd5_dir.iterdir()):
                        dupmd5_dir.rmdir()
                        current_app.logger.info(
                            "Removed empty directory: %s",
                            sanitize_log_value(dupmd5_dir),
                        )
                except (OSError, PermissionError) as e:
                    current_app.logger.warning(
                        "Could not remove directory %s: %s",
                        sanitize_log_value(dupmd5_dir),
                        sanitize_log_value(e),
                    )
            
            if deleted_count > 0:
                flash(f"Successfully deleted {deleted_count} duplicate files, freeing {_format_size(deleted_size)} of space.", "success")
            else:
                flash("No duplicate files found to delete.", "info")
                
        except Exception as e:
            current_app.logger.error(
                "Error deleting duplicates: %s",
                sanitize_log_value(e),
            )
            flash(f"Error deleting duplicates: {str(e)}", "error")
    
    return redirect(url_for("admin.disk_usage"))


@roles_required("admin")
def delete_old_processed_zips():
    """Preview or delete processed ZIP files after DB-confirmed retention checks."""
    if request.method == "POST":
        try:
            # Get the processed directory
            processed_dir = Path(current_app.root_path) / "files" / "zips_upload_processed"
            
            if not processed_dir.exists():
                flash("Processed ZIP directory not found.", "warning")
                return redirect(url_for("admin.disk_usage"))

            retention_days = _parse_positive_int(request.form.get("retention_days"), default=30)
            limit = _parse_optional_int(request.form.get("limit"))
            dry_run = request.form.get("dry_run", "true").lower() != "false"

            with get_db_session() as db_session:
                result = cleanup_processed_zip_archives(
                    db_session,
                    processed_dir=processed_dir,
                    retention_days=retention_days,
                    dry_run=dry_run,
                    limit=limit,
                )

            if dry_run and _wants_zip_cleanup_modal():
                return render_template(
                    "admin/partials/processed_zip_cleanup_modal.html",
                    result=result,
                    retention_days=retention_days,
                    limit=limit,
                    size_label=_format_size(result["eligible_size_bytes"]),
                )

            if dry_run:
                flash(
                    "Preview found "
                    f"{result['eligible']} DB-confirmed processed ZIP files older than "
                    f"{retention_days} days, totaling {_format_size(result['eligible_size_bytes'])}. "
                    f"Skipped {result['skipped']} and saw {result['errors']} errors.",
                    "info",
                )
            elif result["deleted"] > 0:
                current_app.logger.info(
                    "Deleted %s DB-confirmed processed ZIP files older than %s days, freeing %s",
                    sanitize_log_value(result["deleted"]),
                    sanitize_log_value(retention_days),
                    sanitize_log_value(_format_size(result["deleted_size_bytes"])),
                )
                flash(
                    f"Deleted {result['deleted']} DB-confirmed processed ZIP files, "
                    f"freeing {_format_size(result['deleted_size_bytes'])}. "
                    f"Skipped {result['skipped']} and saw {result['errors']} errors.",
                    "success",
                )
            else:
                if result["errors"] > 0:
                    flash(
                        f"No ZIP files were deleted. Skipped {result['skipped']} and saw {result['errors']} errors.",
                        "warning",
                    )
                else:
                    flash("No DB-confirmed processed ZIP files matched the retention policy.", "info")
                
        except Exception as e:
            current_app.logger.error(
                "Error deleting old processed ZIP files: %s",
                sanitize_log_value(e),
            )
            flash(f"Error deleting old processed ZIP files: {str(e)}", "error")
    
    return redirect(url_for("admin.disk_usage"))


def _wants_zip_cleanup_modal() -> bool:
    return request.headers.get("HX-Request") == "true" or request.form.get("response") == "modal"


def cleanup_processed_zip_archives(
    db_session,
    *,
    processed_dir: Path,
    retention_days: int = 30,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict:
    """Preview/delete processed ZIP archives after confirming ingestion in DB."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = {
        "dry_run": dry_run,
        "retention_days": retention_days,
        "scanned": 0,
        "eligible": 0,
        "eligible_size_bytes": 0,
        "deleted": 0,
        "deleted_size_bytes": 0,
        "skipped": 0,
        "errors": 0,
        "items": [],
    }

    processed_dir = Path(processed_dir)
    if not processed_dir.exists():
        return result

    pending_db_checks: list[tuple[dict, Path, str]] = []

    def flush_pending_db_checks() -> None:
        if not pending_db_checks:
            return
        statuses = _processed_zip_archive_statuses(db_session, pending_db_checks)
        for item, zip_file, db_filename in pending_db_checks:
            is_eligible, reason, zip_file_id = statuses.get(
                db_filename,
                (False, "missing_zip_file_row", None),
            )
            item["reason"] = reason
            item["zip_file_id"] = zip_file_id
            if not is_eligible:
                result["skipped"] += 1
                result["items"].append(item)
                continue

            result["eligible"] += 1
            result["eligible_size_bytes"] += item["size_bytes"]
            if dry_run:
                item["status"] = "eligible"
                result["items"].append(item)
                continue

            try:
                zip_file.unlink()
                item["status"] = "deleted"
                result["deleted"] += 1
                result["deleted_size_bytes"] += item["size_bytes"]
                current_app.logger.info(
                    "Deleted processed ZIP archive %s after DB confirmation zip_file_id=%s",
                    sanitize_log_value(zip_file.name),
                    item["zip_file_id"],
                )
            except Exception as exc:
                result["errors"] += 1
                item["status"] = "error"
                item["reason"] = type(exc).__name__
                item["error"] = str(exc)
                current_app.logger.error(
                    "Failed to delete DB-confirmed processed ZIP archive %s: %s",
                    sanitize_log_value(zip_file),
                    sanitize_log_value(exc),
                    exc_info=True,
                )
            result["items"].append(item)
        pending_db_checks.clear()

    for date_dir in sorted(path for path in processed_dir.iterdir() if path.is_dir()):
        try:
            dir_date = datetime.strptime(date_dir.name, "%Y_%m_%d").replace(tzinfo=timezone.utc)
        except ValueError:
            current_app.logger.warning(
                "Skipping processed ZIP directory with unexpected format: %s",
                sanitize_log_value(date_dir.name),
            )
            continue

        for zip_file in sorted(date_dir.glob("*.zip")):
            if limit is not None and result["scanned"] >= limit:
                flush_pending_db_checks()
                return result
            result["scanned"] += 1

            item = {
                "filename": zip_file.name,
                "path": str(zip_file.relative_to(processed_dir.parent)),
                "status": "skipped",
                "reason": None,
                "zip_file_id": None,
                "size_bytes": 0,
            }
            try:
                file_size = zip_file.stat().st_size
                item["size_bytes"] = file_size

                if dir_date >= cutoff_date:
                    item["reason"] = "retention_not_met"
                    result["skipped"] += 1
                    result["items"].append(item)
                    continue

                pending_db_checks.append((item, zip_file, clean_filename(zip_file.name)))
                if len(pending_db_checks) >= ZIP_ARCHIVE_DB_CHECK_BATCH_SIZE:
                    flush_pending_db_checks()
            except Exception as exc:
                result["errors"] += 1
                item["status"] = "error"
                item["reason"] = type(exc).__name__
                item["error"] = str(exc)
                current_app.logger.error(
                    "Failed processed ZIP archive retention check/delete for %s: %s",
                    sanitize_log_value(zip_file),
                    sanitize_log_value(exc),
                    exc_info=True,
                )
            result["items"].append(item)

        try:
            if not dry_run and not any(date_dir.iterdir()):
                date_dir.rmdir()
        except (OSError, PermissionError) as exc:
            current_app.logger.warning(
                "Could not remove processed ZIP archive directory %s: %s",
                sanitize_log_value(date_dir),
                sanitize_log_value(exc),
            )

    flush_pending_db_checks()
    return result


def _processed_zip_archive_statuses(
    db_session,
    candidates: list[tuple[dict, Path, str]],
) -> dict[str, tuple[bool, str, int | None]]:
    """Return DB-confirmed cleanup status for many ZIP archives in one batch."""
    db_filenames = {db_filename for _, _, db_filename in candidates}
    raw_filenames = {zip_path.name for _, zip_path, _ in candidates}
    if not db_filenames:
        return {}

    zip_rows = (
        db_session.query(
            ZipFile.id.label("zip_file_id"),
            ZipFile.zip_filename.label("zip_filename"),
            PatientEncounters.id.label("encounter_id"),
        )
        .outerjoin(PatientEncounters, PatientEncounters.zip_file_id == ZipFile.id)
        .filter(ZipFile.zip_filename.in_(db_filenames))
        .all()
    )
    zip_by_filename = {row.zip_filename: row for row in zip_rows}
    encounter_ids = {row.encounter_id for row in zip_rows if row.encounter_id is not None}

    encounter_ids_with_images = set()
    encounter_ids_with_pdfs = set()
    if encounter_ids:
        encounter_ids_with_images = {
            encounter_id
            for (encounter_id,) in db_session.query(EncounterFile.patient_encounter_id)
            .filter(EncounterFile.patient_encounter_id.in_(encounter_ids))
            .distinct()
            .all()
        }
        encounter_ids_with_pdfs = {
            encounter_id
            for (encounter_id,) in db_session.query(EncounterFilePDF.patient_encounter_id)
            .filter(EncounterFilePDF.patient_encounter_id.in_(encounter_ids))
            .distinct()
            .all()
        }

    job_filenames = db_filenames | raw_filenames
    active_job_filenames = {
        filename
        for (filename,) in db_session.query(JobItem.filename)
        .filter(JobItem.filename.in_(job_filenames))
        .filter(JobItem.state.in_(ACTIVE_JOB_ITEM_STATES))
        .distinct()
        .all()
    }

    statuses: dict[str, tuple[bool, str, int | None]] = {}
    for _, zip_path, db_filename in candidates:
        zip_row = zip_by_filename.get(db_filename)
        if zip_row is None:
            statuses[db_filename] = (False, "missing_zip_file_row", None)
            continue
        if zip_row.encounter_id is None:
            statuses[db_filename] = (False, "missing_patient_encounter", zip_row.zip_file_id)
            continue
        if (
            zip_row.encounter_id not in encounter_ids_with_images
            and zip_row.encounter_id not in encounter_ids_with_pdfs
        ):
            statuses[db_filename] = (False, "missing_extracted_encounter_file", zip_row.zip_file_id)
            continue
        if zip_path.name in active_job_filenames or db_filename in active_job_filenames:
            statuses[db_filename] = (False, "active_job_item_exists", zip_row.zip_file_id)
            continue
        statuses[db_filename] = (True, "eligible", zip_row.zip_file_id)

    return statuses


def _processed_zip_archive_status(db_session, zip_path: Path) -> tuple[bool, str, ZipFile | None]:
    db_filename = clean_filename(zip_path.name)
    zip_file = db_session.query(ZipFile).filter(ZipFile.zip_filename == db_filename).one_or_none()
    if zip_file is None:
        return False, "missing_zip_file_row", None

    encounter = zip_file.patient_encounter
    if encounter is None:
        return False, "missing_patient_encounter", zip_file

    if not encounter.encounter_files and not encounter.encounter_file_pdfs:
        return False, "missing_extracted_encounter_file", zip_file

    active_job_item = (
        db_session.query(JobItem.id)
        .filter(JobItem.filename.in_({zip_path.name, db_filename}))
        .filter(JobItem.state.in_(ACTIVE_JOB_ITEM_STATES))
        .first()
    )
    if active_job_item is not None:
        return False, "active_job_item_exists", zip_file

    return True, "eligible", zip_file


def _parse_positive_int(value, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _parse_optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(parsed, 0)
