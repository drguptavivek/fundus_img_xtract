# reports/routes.py
import os
from pathlib import Path
from flask import abort, send_from_directory
from werkzeug.utils import secure_filename

from auth.roles import roles_required
from . import bp

# Reuse the same locations you configured for split PDFs
# (these were moved to .env in your earlier steps)
from process_pdfs import DR_PDF_DIR, GLAUCOMA_PDF_DIR  # Path objects

def _safe_file(base_dir: Path, filename: str) -> tuple[str, str]:
    """
    Prevent path traversal & ensure file exists inside base_dir.
    Returns (directory_str, filename_str) for send_from_directory.
    """
    # Strip any path parts the client may try to sneak in
    fname = secure_filename(os.path.basename(filename))
    full = base_dir / fname
    if not full.exists() or not full.is_file():
        abort(404)
    return (str(base_dir), fname)

@bp.route("/dr/<path:filename>", methods=["GET"])
@roles_required("admin")
def serve_dr_pdf(filename: str):
    directory, fname = _safe_file(DR_PDF_DIR, filename)
    # Serve inline (not attachment), browser will open in a new tab when link has target=_blank
    return send_from_directory(directory=directory, path=fname, mimetype="application/pdf", as_attachment=False)

@bp.route("/glaucoma/<path:filename>", methods=["GET"])
@roles_required("admin")
def serve_glaucoma_pdf(filename: str):
    directory, fname = _safe_file(GLAUCOMA_PDF_DIR, filename)
    return send_from_directory(directory=directory, path=fname, mimetype="application/pdf", as_attachment=False)
