# media/routes.py

import os
from pathlib import Path
from flask import abort, Response
from flask_login import current_user
from sqlalchemy import select
from uuid import UUID  # only used by EncounterFile route
from auth.roles import roles_required

# Import utility functions from fileUtils
from utils.fileUtils import  _ensure_under_root, _send_file_with_headers,   abs_from_parts
from utils.paths import get_image_path_by_uuid
from utils.utilsImgServe import directImgFinalByUUID, directImgOrigByUUID

from . import bp

from models import (
    ALLOWED_IMAGE_EXT, IMAGE_DIR, PDF_DIR, DIRECT_UPLOAD_DIR,
    Session, EncounterFile, DirectImageUpload
)


# Serve ZIP_Upload images by UUID
@bp.route("/encounter/img/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_file_by_uuid(uuid: str):
    try:
        ef = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
    finally:
        db.close()

    if not ef or not ef.filename:
        abort(404)

    fname = os.path.basename(ef.filename)
    if fname != ef.filename:
        abort(404)

    ext = Path(fname).suffix.lower()
    file_type = (ef.file_type or "").lower()

    if file_type.startswith("image") or ext in ALLOWED_IMAGE_EXT:
        base_dir = IMAGE_DIR
        mimetype = None  # let mimetypes decide
    elif ext == ".pdf" or file_type == "pdf":
        base_dir = PDF_DIR
        mimetype = "application/pdf"
    else:
        abort(404)

    full = (base_dir / fname).resolve()
    _ensure_under_root(full, base_dir)

    return _send_file_with_headers(full, mimetype=mimetype)


# ---------------- New direct-upload ID/UUID-based routes ----------------
@bp.route("/direct_upload/img/<uuid_str>", methods=["GET"])
@roles_required("contributor", "data_manager", "admin")
def serve_img_by_uuid_preferring_edited(uuid_str: str):
    # Sanity-check UUID format
    try:
        directImgFinalByUUID(uuid_str)
    except Exception:
        abort(404)
