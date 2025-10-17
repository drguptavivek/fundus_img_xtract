"""Admin disk usage assessment routes."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

from flask import current_app, render_template, request, jsonify, flash, redirect, url_for

from auth.roles import roles_required
from models import Session, ZipFile


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
        current_app.logger.info(f"Files directory found: {files_root.resolve()}")
    else:
        current_app.logger.warning(f"Files directory not found at: {files_root.resolve()}")
    
    # Get logs directory
    configured_logs = current_app.config.get("LOG_VIEWER_ROOT")
    if configured_logs:
        logs_root = Path(configured_logs)
    else:
        logs_root = Path(current_app.root_path) / "logs"
    
    # Check if logs directory exists and add to list
    if logs_root.exists():
        directories.append(logs_root.resolve())
        current_app.logger.info(f"Logs directory found: {logs_root.resolve()}")
    else:
        current_app.logger.warning(f"Logs directory not found at: {logs_root.resolve()}")
    
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


def _analyze_directory(path: Path, parent_path: Path = None, level: int = 0, expanded_dirs: set = None) -> List[Dict]:
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
    
    if parent_path is None:
        parent_path = path.parent
    
    directories = []
    
    try:
        for entry in sorted(path.iterdir()):
            if entry.is_dir():
                try:
                    size_bytes = _get_directory_size(entry)
                    stat = entry.stat()
                    
                    # Create a unique identifier for this directory
                    dir_id = str(entry.relative_to(parent_path))
                    
                    dir_info = {
                        "name": entry.name,
                        "path": str(entry.relative_to(parent_path)),
                        "level": level,
                        "size_bytes": size_bytes,
                        "size_formatted": _format_size(size_bytes),
                        "dir_count": _count_directories(entry),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        "has_subdirs": any(e.is_dir() for e in entry.iterdir()),
                        "expanded": dir_id in expanded_dirs,
                        "usage_percentage": 0,  # Will be calculated later
                    }
                    
                    # Recursively analyze subdirectories if this directory is expanded
                    if dir_info["expanded"] and dir_info["has_subdirs"]:
                        dir_info["subdirectories"] = _analyze_directory(
                            entry, parent_path, level + 1, expanded_dirs
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
    current_app.logger.info(f"Directories to analyze: {[str(d) for d in directories_to_analyze]}")
    
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
    
    # Analyze each base directory
    for base_dir in directories_to_analyze:
        current_app.logger.info(f"Analyzing directory: {base_dir}")
        if base_dir.exists():
            # Get size and directory count for this base directory
            dir_size = _get_directory_size(base_dir)
            dir_count = _count_directories(base_dir)
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
                "has_subdirs": True,
                "expanded": base_dir.name in expanded_dirs,
            }
            
            # Get subdirectories recursively
            base_dir_info["subdirectories"] = _analyze_directory(
                base_dir, base_dir.parent, 1, expanded_dirs
            )
            
            all_directories.append(base_dir_info)
            current_app.logger.info(f"Added directory to results: {base_dir.name} ({base_dir_info['size_formatted']})")
        else:
            current_app.logger.warning(f"Directory does not exist: {base_dir}")
    
    current_app.logger.info(f"Total directories found: {len(all_directories)}")
    
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
        except Exception:
            pass
        return False
    
    has_dupmd5 = has_dupmd5_directory(all_directories) or has_dupmd5_at_root()
    
    # Check if there are old processed ZIP files (older than 1 month)
    def has_old_processed_zips(directories):
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        for directory in directories:
            # Check if this is the zips_upload_processed directory
            if directory["name"] == "zips_upload_processed":
                # Check subdirectories (date directories)
                for subdir in directory.get("subdirectories", []):
                    # Parse the date from directory name (format: YYYY_MM_DD)
                    try:
                        dir_date = datetime.strptime(subdir["name"], "%Y_%m_%d").replace(tzinfo=timezone.utc)
                        if dir_date < cutoff_date:
                            return True
                    except ValueError:
                        continue
            # Recursively check subdirectories
            if directory.get("subdirectories") and has_old_processed_zips(directory["subdirectories"]):
                return True
        return False
    
    has_old_zips = has_old_processed_zips(all_directories)
    
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
                current_app.logger.info(f"Processing duplicate directory: {dupmd5_dir}")
                
                for file_path in dupmd5_dir.iterdir():
                    if file_path.is_file():
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            deleted_count += 1
                            deleted_size += file_size
                            current_app.logger.info(f"Deleted duplicate file: {file_path.name}")
                        except (OSError, PermissionError) as e:
                            current_app.logger.error(f"Failed to delete {file_path}: {e}")
                
                # Try to remove the directory if it's empty
                try:
                    if not any(dupmd5_dir.iterdir()):
                        dupmd5_dir.rmdir()
                        current_app.logger.info(f"Removed empty directory: {dupmd5_dir}")
                except (OSError, PermissionError) as e:
                    current_app.logger.warning(f"Could not remove directory {dupmd5_dir}: {e}")
            
            if deleted_count > 0:
                flash(f"Successfully deleted {deleted_count} duplicate files, freeing {_format_size(deleted_size)} of space.", "success")
            else:
                flash("No duplicate files found to delete.", "info")
                
        except Exception as e:
            current_app.logger.error(f"Error deleting duplicates: {e}")
            flash(f"Error deleting duplicates: {str(e)}", "error")
    
    return redirect(url_for("admin.disk_usage"))


@roles_required("admin")
def delete_old_processed_zips():
    """Delete processed ZIP files older than 1 month."""
    if request.method == "POST":
        try:
            # Get the processed directory
            processed_dir = Path(current_app.root_path) / "files" / "zips_upload_processed"
            
            if not processed_dir.exists():
                flash("Processed ZIP directory not found.", "warning")
                return redirect(url_for("admin.disk_usage"))
            
            # Calculate the cutoff date (1 month ago)
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
            
            deleted_count = 0
            deleted_size = 0
            deleted_dirs = []
            
            # Get database session to check ZIP file dates
            db_session = Session()
            
            try:
                # Iterate through all date subdirectories in the processed directory
                for date_dir in processed_dir.iterdir():
                    if not date_dir.is_dir():
                        continue
                    
                    # Parse the date from directory name (format: YYYY_MM_DD)
                    try:
                        dir_date = datetime.strptime(date_dir.name, "%Y_%m_%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        # Skip directories that don't match the expected format
                        current_app.logger.warning(f"Skipping directory with unexpected format: {date_dir.name}")
                        continue
                    
                    # Check if this directory is older than 1 month
                    if dir_date < cutoff_date:
                        dir_size = 0
                        dir_file_count = 0
                        
                        # Delete all ZIP files in this directory
                        for zip_file in date_dir.glob("*.zip"):
                            try:
                                file_size = zip_file.stat().st_size
                                zip_file.unlink()
                                deleted_count += 1
                                dir_size += file_size
                                dir_file_count += 1
                                current_app.logger.info(f"Deleted processed ZIP file: {zip_file.name}")
                            except (OSError, PermissionError) as e:
                                current_app.logger.error(f"Failed to delete {zip_file}: {e}")
                        
                        # Try to remove the directory if it's empty
                        try:
                            if not any(date_dir.iterdir()):
                                date_dir.rmdir()
                                current_app.logger.info(f"Removed empty directory: {date_dir}")
                        except (OSError, PermissionError) as e:
                            current_app.logger.warning(f"Could not remove directory {date_dir}: {e}")
                        
                        if dir_file_count > 0:
                            deleted_size += dir_size
                            deleted_dirs.append(f"{date_dir.name} ({dir_file_count} files)")
                
                # Log the action
                if deleted_count > 0:
                    current_app.logger.info(f"Deleted {deleted_count} processed ZIP files older than 1 month, freeing {_format_size(deleted_size)} of space")
                    flash(f"Successfully deleted {deleted_count} processed ZIP files from {len(deleted_dirs)} directories, freeing {_format_size(deleted_size)} of space.", "success")
                    
                    # Show which directories were cleaned
                    if deleted_dirs:
                        current_app.logger.info(f"Cleaned directories: {', '.join(deleted_dirs)}")
                else:
                    flash("No processed ZIP files older than 1 month found to delete.", "info")
                    
            finally:
                db_session.close()
                
        except Exception as e:
            current_app.logger.error(f"Error deleting old processed ZIP files: {e}")
            flash(f"Error deleting old processed ZIP files: {str(e)}", "error")
    
    return redirect(url_for("admin.disk_usage"))