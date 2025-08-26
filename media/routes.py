# media/routes.py
import os
from pathlib import Path
from flask import abort, send_from_directory
from werkzeug.utils import secure_filename
from . import bp

# Use your existing configured IMAGE_DIR from models.py
from models import IMAGE_DIR  # Path object

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

def _safe_image(base_dir: Path, filename: str) -> tuple[str, str]:
    fname = secure_filename(os.path.basename(filename))
    full = base_dir / fname
    if not full.exists() or not full.is_file() or full.suffix.lower() not in ALLOWED_IMAGE_EXT:
        abort(404)
    return (str(base_dir), fname)

@bp.route("/img/<path:filename>", methods=["GET"])
def serve_image(filename: str):
    directory, fname = _safe_image(IMAGE_DIR, filename)
    # Let the browser display the image inline; open in new tab via target=_blank in templates
    return send_from_directory(directory=directory, path=fname, as_attachment=False)
