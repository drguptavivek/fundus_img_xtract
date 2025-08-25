# initialize.py
import os
import sys
import subprocess
from pathlib import Path

# Define paths (relative to this file)
BASE_DIR = Path(__file__).parent.resolve()
processed_dir = BASE_DIR / "files" / "processed"
uploaded_dir  = BASE_DIR / "files" / "uploaded"
db_path       = BASE_DIR / "zip_processing.db"
models_script = BASE_DIR / "models.py"


def ensure_directories() -> None:
    """Create required directories if they don't exist."""
    for d in (processed_dir, uploaded_dir):
        d.mkdir(parents=True, exist_ok=True)
        print(f"Ensured directory exists: {d}")


def run_models_script(script_path: Path) -> None:
    """Run models.py with the current Python interpreter."""
    if not script_path.is_file():
        print(f"Script not found: {script_path}")
        raise SystemExit(1)

    print(f"Executing {script_path} with {sys.executable} ...")
    try:
        subprocess.run([sys.executable, str(script_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {script_path.name} exited with status {e.returncode}")
        raise SystemExit(e.returncode)


def ensure_db_exists() -> None:
    """Create DB (via models.py) only if it doesn't already exist."""
    if db_path.exists():
        print(f"DB already present: {db_path}")
        return
    print(f"DB not found, creating: {db_path}")
    run_models_script(models_script)


if __name__ == "__main__":
    ensure_directories()
    ensure_db_exists()
