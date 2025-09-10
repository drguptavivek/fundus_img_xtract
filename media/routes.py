# media/routes.py

import os
from pathlib import Path
from flask import abort, Response
from flask_login import current_user
from sqlalchemy import select
from uuid import UUID  # only used by EncounterFile route
from auth.roles import roles_required

# Import utility functions from fileUtils
from utils.fileUtils import  _ensure_under_root, _send_file_with_headers, _serve_path,  get_image_folder_path_by_uuid, get_image_path_by_uuid, abs_from_parts

from . import bp

from models import (
    ALLOWED_IMAGE_EXT, IMAGE_DIR, PDF_DIR, DIRECT_UPLOAD_DIR,
    Session, EncounterFile, DirectImageUpload
)



@bp.route("/img/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_img_by_uuid(uuid: str):
    """ 
    Search in EncounterFile for UUID. If Found serve image based on encounterfiles.filename from zipFile_upload subDir
    Else Search in DirectImageUploads - Check UUID. If UUID Check edited_filename. If editedFilename, serve based on edited_filename, else serve based on filename
    """
    # First try to find the image in EncounterFile (ZIP uploads)
    db = Session()
    try:
        # Try to find in EncounterFile first
        ef = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
        if ef and ef.filename:
            # Get the image path using our utility function
            image_path = get_image_path_by_uuid(uuid)
            if image_path:
                abs_path = Path(image_path).resolve()
                return _send_file_with_headers(abs_path)
        
        # If not found in EncounterFile, try DirectImageUpload
        diu = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if diu:
            # Prefer edited if present, else original
            if diu.edited_filename:
                try:
                    ap = abs_from_parts(diu.folder_rel, diu.edited_filename, "edited").resolve()
                    return _serve_path(ap)
                except Exception:
                    # Fall back to original if edited is missing
                    pass

            ap = abs_from_parts(diu.folder_rel, diu.filename, "orig")
            return _serve_path(ap)
    finally:
        db.close()
    
    # If we get here, the image wasn't found
    abort(404)



# Serve ZIP_Upload images by UUID
@bp.route("/file/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_file_by_uuid(uuid: str):
    """
    Serve an EncounterFile by UUID from IMAGE_DIR, admin-only.
    """
    db = Session()
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



@bp.route("/direct_upload/img_orig/<int:upload_id>", methods=["GET"])
@roles_required("contributor", "data_manager", "admin")
def serve_img_orig(upload_id: int):
    db = Session()
    try:
        q = select(DirectImageUpload).where(DirectImageUpload.id == upload_id)
        if not current_user.has_role("admin", "data_manager"):
            q = q.where(DirectImageUpload.uploader_id == current_user.id)
        u = db.execute(q).scalar_one_or_none()
        if not u:
            abort(404)

        ap = abs_from_parts(u.folder_rel, u.filename, "orig")
        return _serve_path(ap)
    finally:
        db.close()


@bp.route("/direct_upload/img_edited/<int:upload_id>", methods=["GET"])
@roles_required("contributor", "data_manager", "admin")
def serve_img_edited(upload_id: int):
    db = Session()
    try:
        q = select(DirectImageUpload).where(DirectImageUpload.id == upload_id)
        if not current_user.has_role("admin", "data_manager"):
            q = q.where(DirectImageUpload.uploader_id == current_user.id)
        u = db.execute(q).scalar_one_or_none()
        if not u or not u.edited_filename:
            abort(404)

        ap = abs_from_parts(u.folder_rel, u.edited_filename, "edited")
        return _serve_path(ap)
    finally:
        db.close()


@bp.route("/direct_upload/img/<uuid_str>", methods=["GET"])
@roles_required("contributor", "data_manager", "admin")
def serve_img_by_uuid_preferring_edited(uuid_str: str):
    # Sanity-check UUID format
    try:
        _ = UUID(uuid_str)
    except Exception:
        abort(404)

    db = Session()
    try:
        q = select(DirectImageUpload).where(DirectImageUpload.uuid == str(uuid_str))
        if not current_user.has_role("admin", "data_manager"):
            q = q.where(DirectImageUpload.uploader_id == current_user.id)
        u = db.execute(q).scalar_one_or_none()
        if not u:
            abort(404)

        # Prefer edited if present, else original
        if u.edited_filename:
            try:
                ap = abs_from_parts(u.folder_rel, u.edited_filename, "edited").resolve()
                return _serve_path(ap)
            except Exception:
                # Fall back to original if edited is missing
                pass

        ap = abs_from_parts(u.folder_rel, u.filename, "orig")
        return _serve_path(ap)
    finally:
        db.close()
