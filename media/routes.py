# media/routes.py

import os
from pathlib import Path
from flask import abort, current_app, send_from_directory, Response
from flask_login import current_user
from sqlalchemy import select
from uuid import UUID  # only used by EncounterFile route

from auth.roles import roles_required
from . import bp

from models import (
    IMAGE_DIR, PDF_DIR, DIRECT_UPLOAD_DIR,
    Session, EncounterFile, DirectImageUpload
)
from direct_uploads.paths import abs_from_parts


ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


# ---------------- Admin-only legacy image & file serving ----------------

@bp.route("/img/<path:filename>", methods=["GET"])
@roles_required("admin")
def serve_image(filename: str):
    """
    Serve an image from IMAGE_DIR by basename, admin-only.
    """
    fname = os.path.basename(filename)
    if fname != filename:
        abort(404)
    if Path(fname).suffix.lower() not in ALLOWED_IMAGE_EXT:
        abort(404)

    full = IMAGE_DIR / fname
    if not full.exists() or not full.is_file():
        abort(404)

    return send_from_directory(directory=str(IMAGE_DIR), path=fname, as_attachment=False)


@bp.route("/file/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_file_by_uuid(uuid: str):
    """
    Serve an EncounterFile by UUID from IMAGE_DIR or PDF_DIR, admin-only.
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
    if (ef.file_type or '').lower().startswith('image') or ext in ALLOWED_IMAGE_EXT:
        base_dir = IMAGE_DIR
        mimetype = None
    elif ext == '.pdf' or (ef.file_type or '').lower() == 'pdf':
        base_dir = PDF_DIR
        mimetype = "application/pdf"
    else:
        abort(404)

    full = base_dir / fname
    if not full.exists() or not full.is_file():
        abort(404)

    return send_from_directory(directory=str(base_dir), path=fname, as_attachment=False, mimetype=mimetype)


# ---------------- New direct-upload ID-based routes (no path params) ----------------
def _serve_path(ap) -> Response:
    if not ap.exists() or not ap.is_file() or ap.suffix.lower() not in ALLOWED_IMAGE_EXT:
        abort(404)
    root = DIRECT_UPLOAD_DIR.resolve()
    rel_to_root = ap.resolve().relative_to(root)
    resp: Response = send_from_directory(str(root), str(rel_to_root), as_attachment=False)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Cache-Control", "private, max-age=600")
    return resp

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

        # ✅ Use folder_rel + filename
        ap = abs_from_parts(u.folder_rel, u.filename, "orig")
        if not ap.exists() or not ap.is_file():
            abort(404)

        root = DIRECT_UPLOAD_DIR.resolve()
        rel_to_root = ap.resolve().relative_to(root)
        resp: Response = send_from_directory(
            str(root),
            str(rel_to_root),
            as_attachment=False
        )
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Cache-Control", "private, max-age=600")
        return resp
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

@bp.route("/direct_upload/imgs/uuid/<uuid_str>", methods=["GET"])
@roles_required("contributor", "data_manager", "admin")
def serve_img_by_uuid_preferring_edited(uuid_str: str):
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

        # prefer edited if present, else original
        if u.edited_filename:
            try:
                ap = abs_from_parts(u.folder_rel, u.edited_filename, "edited")
                return _serve_path(ap)
            except Exception:
                pass

        ap = abs_from_parts(u.folder_rel, u.filename, "orig")
        return _serve_path(ap)
    finally:
        db.close()
        

@bp.route("/direct_upload/uuid/<uuid_str>", methods=["GET"])
@roles_required("contributor", "data_manager", "admin")
def direct_upload_uuid():
    # TODO
    print("direct_upload by UUID Done")