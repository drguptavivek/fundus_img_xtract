# reset.py
import shutil
from pathlib import Path
from datetime import datetime

# Base directory of your project
BASE_DIR = Path(__file__).resolve().parent

# Paths
DB_FILE = BASE_DIR / "zip_processing.db"
FILES_DIR = BASE_DIR / "files"
UPLOAD_DIR = FILES_DIR / "uploaded"
PROCESSED_DIR = FILES_DIR / "processed"
LOG_FILE = BASE_DIR / "process_log.txt"

def reset_database():
    """Delete the SQLite database if it exists."""
    if DB_FILE.exists():
        DB_FILE.unlink()
        print(f"Deleted database: {DB_FILE}")
    else:
        print("No database file found to delete.")

def reset_logger():
    """Delete the process log file if it exists."""
    if LOG_FILE.exists():
        LOG_FILE.unlink()
        print(f"Deleted log file: {LOG_FILE}")
    else:
        print("No log file found to delete.")

def reset_files():
    """
    Clear all subfolders under /files except /uploaded.
    Also move ZIPs from /processed and /dupmd5_* back into /uploaded.
    """
    if not FILES_DIR.exists():
        print("No 'files' directory found, skipping.")
        return

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Move processed zips back
    if PROCESSED_DIR.exists():
        for item in PROCESSED_DIR.glob("*.zip"):
            target = UPLOAD_DIR / item.name
            shutil.move(str(item), str(target))
            print(f"Moved back from processed: {item.name}")
    
    # Move dupmd5_* zips back
    for dup_dir in FILES_DIR.glob("dupmd5_*"):
        if dup_dir.is_dir():
            for item in dup_dir.glob("*.zip"):
                target = UPLOAD_DIR / item.name
                shutil.move(str(item), str(target))
                print(f"Moved back from {dup_dir.name}: {item.name}")
            # remove the empty dup dir
            shutil.rmtree(dup_dir)
            print(f"Removed duplicate dir: {dup_dir}")

    # Clear other subdirectories except uploaded
    for subdir in FILES_DIR.iterdir():
        if subdir.is_dir() and subdir.name not in ["uploaded"]:
            if subdir.exists():
                shutil.rmtree(subdir)
                subdir.mkdir(parents=True, exist_ok=True)
                print(f"Cleared: {subdir}")

    print("Files reset complete (uploaded preserved).")

if __name__ == "__main__":
    print("=== Resetting environment ===")
    reset_database()
    reset_files()
    reset_logger()
    print("=== Reset complete ===")
