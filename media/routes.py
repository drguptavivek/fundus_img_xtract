# media/routes.py

import os
import mimetypes
from pathlib import Path
from flask import abort, send_file, send_from_directory, Response
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


# ---------------- Helpers ----------------

def _send_file_with_headers(abs_path: Path, mimetype: str | None = None) -> Response:
    """Cross-platform safe file send with sensible headers."""
    abs_path = abs_path.resolve()
    if not abs_path.exists() or not abs_path.is_file():
        abort(404)

    # Guess type if not provided
    guessed, _ = mimetypes.guess_type(abs_path.name)
    mt = mimetype or guessed or "application/octet-stream"

    resp: Response = send_file(
        abs_path,
        mimetype=mt,
        as_attachment=False,
        conditional=True,   # enables range/If-Modified-Since
        etag=True,
        last_modified=abs_path.stat().st_mtime
    )
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Cache-Control", "private, max-age=600")
    return resp


def _ensure_under_root(abs_path: Path, root: Path) -> None:
    """Ensure abs_path is inside root (prevents traversal / wrong volume)."""
    abs_path = abs_path.resolve()
    root = root.resolve()
    try:
        abs_path.relative_to(root)
    except Exception:
        abort(404)


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

    ext = Path(fname).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        abort(404)

    full = (IMAGE_DIR / fname).resolve()
    _ensure_under_root(full, IMAGE_DIR)

    return _send_file_with_headers(full)


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

def _serve_path(ap: Path) -> Response:
    """
    Serve a direct-upload image path under DIRECT_UPLOAD_DIR safely.
    Works on Windows/macOS/Linux.
    """
    ap = ap.resolve()

    # Must live under DIRECT_UPLOAD_DIR
    _ensure_under_root(ap, DIRECT_UPLOAD_DIR)

    # Basic validation
    if ap.suffix.lower() not in ALLOWED_IMAGE_EXT:
        abort(404)

    return _send_file_with_headers(ap)


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
