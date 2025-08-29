# media/routes.py
import os
from pathlib import Path
from flask import abort, send_from_directory
from werkzeug.utils import secure_filename

from auth.roles import roles_required
from . import bp

# Use your existing configured IMAGE_DIR from models.py
from models import IMAGE_DIR, PDF_DIR, Session, EncounterFile  # Path objects and DB

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

def _safe_image(base_dir: Path, filename: str) -> tuple[str, str]:
    fname = secure_filename(os.path.basename(filename))
    full = base_dir / fname
    if not full.exists() or not full.is_file() or full.suffix.lower() not in ALLOWED_IMAGE_EXT:
        abort(404)
    return (str(base_dir), fname)

@bp.route("/img/<path:filename>", methods=["GET"])
@roles_required("admin")
def serve_image(filename: str):
    directory, fname = _safe_image(IMAGE_DIR, filename)
    # Let the browser display the image inline; open in new tab via target=_blank in templates
    return send_from_directory(directory=directory, path=fname, as_attachment=False)


@bp.route("/file/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_file_by_uuid(uuid: str):
    """Serve an EncounterFile by its UUID, selecting the correct base dir and mimetype."""
    db = Session()
    try:
        ef = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
    finally:
        db.close()

    if not ef or not ef.filename:
        abort(404)

    fname = secure_filename(os.path.basename(ef.filename))
    ext = Path(fname).suffix.lower()
    # Decide location and mimetype
    if (ef.file_type or '').lower().startswith('image') or ext in ALLOWED_IMAGE_EXT:
        base_dir = IMAGE_DIR
        mimetype = None  # let Flask detect from extension
    elif ext == '.pdf' or (ef.file_type or '').lower() == 'pdf':
        base_dir = PDF_DIR
        mimetype = "application/pdf"
    else:
        abort(404)

    full = base_dir / fname
    if not full.exists() or not full.is_file():
        abort(404)

    return send_from_directory(directory=str(base_dir), path=fname, as_attachment=False, mimetype=mimetype)


