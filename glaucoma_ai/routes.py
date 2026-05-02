from __future__ import annotations

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from api.glaucoma_ai import load_user_glaucoma_ai_inference_updates, load_user_glaucoma_ai_upload_results
from services.glaucoma_ai_upload import GlaucomaAIUploadSelection, process_glaucoma_ai_uploads
from utils.log_sanitize import sanitize_log_value
from upload_profiles.service import UploadProfileError, get_user_upload_options

from . import bp


@bp.route("/", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def index():
    with get_db_session() as db:
        upload_options = get_user_upload_options(db, current_user.id)
        recent_uploads = _load_web_recent_uploads(db)
    return render_template(
        "glaucoma_ai/upload.html",
        upload_options=upload_options,
        mydriatic_options=_mydriatic_options(upload_options),
        results=None,
        recent_uploads=recent_uploads,
    )


@bp.route("/upload", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def upload():
    try:
        selection = GlaucomaAIUploadSelection(
            project_id=_to_int(request.form.get("project_id")),
            lab_unit_id=_to_int(request.form.get("lab_unit_id")),
            camera_id=_to_int(request.form.get("camera_id")),
            area_id=_to_int(request.form.get("area_id")),
            is_mydriatic=_to_bool(request.form.get("is_mydriatic")),
            profile_id=_to_int(request.form.get("profile_id")) if request.form.get("profile_id") else None,
        )
    except ValueError:
        flash("Project, lab unit, camera, and site are required.", "danger")
        return redirect(url_for("glaucoma_ai.index"), code=303)

    try:
        result = process_glaucoma_ai_uploads(
            files=request.files.getlist("files"),
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=request.remote_addr,
            selection=selection,
            request_url_builder=lambda image_uuid: url_for("media._directImgFinalByUUID", uuid_str=image_uuid),
            thumbnail_url_builder=lambda image_uuid: url_for("media._directImgFinalThumbnailByUUID", uuid_str=image_uuid),
            app=current_app._get_current_object(),
        )
    except UploadProfileError as exc:
        current_app.logger.warning(
            "Glaucoma AI upload rejected for user=%s code=%s",
            sanitize_log_value(current_user.id),
            sanitize_log_value(exc.code),
        )
        flash(exc.message, "danger")
        return redirect(url_for("glaucoma_ai.index"), code=303)

    if result.success_count:
        flash(f"Processed {result.success_count} image(s).", "success")
    if result.error_count:
        flash(f"{result.error_count} image(s) could not be processed.", "warning")

    with get_db_session() as db:
        upload_options = get_user_upload_options(db, current_user.id)
        recent_uploads = _load_web_recent_uploads(db)
    return render_template(
        "glaucoma_ai/upload.html",
        upload_options=upload_options,
        mydriatic_options=_mydriatic_options(upload_options),
        results=result,
        recent_uploads=recent_uploads,
    )


@bp.route("/recent", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def recent_results_partial():
    with get_db_session() as db:
        recent_uploads = _load_web_recent_uploads(db)
    return render_template("glaucoma_ai/_recent_results.html", recent_uploads=recent_uploads)


@bp.route("/recent/results", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def recent_results_json():
    with get_db_session() as db:
        recent_uploads = load_user_glaucoma_ai_inference_updates(db, current_user.id, limit=20, offset=0)
    return jsonify({"items": recent_uploads})


def _load_web_recent_uploads(db) -> list[dict]:
    items = load_user_glaucoma_ai_upload_results(db, current_user.id, limit=20, offset=0, external_urls=False)
    for item in items:
        image_uuid = item.get("image_uuid")
        if image_uuid:
            item["image_url"] = url_for("media._directImgFinalByUUID", uuid_str=image_uuid)
            item["thumbnail_url"] = url_for("media._directImgFinalThumbnailByUUID", uuid_str=image_uuid)
    return items


def _to_int(value: str | None) -> int:
    try:
        parsed = int(value or "")
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid integer") from exc
    if parsed <= 0:
        raise ValueError("invalid integer")
    return parsed


def _to_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _mydriatic_options(upload_options) -> dict:
    profiles = upload_options.profiles or []
    allow_mydriatic = any(profile.get("allow_mydriatic") for profile in profiles)
    allow_non_mydriatic = any(profile.get("allow_non_mydriatic") for profile in profiles)
    defaults = {bool(profile.get("default_is_mydriatic")) for profile in profiles}
    if allow_mydriatic and not allow_non_mydriatic:
        default_is_mydriatic = True
    elif allow_non_mydriatic and not allow_mydriatic:
        default_is_mydriatic = False
    elif len(defaults) == 1:
        default_is_mydriatic = defaults.pop()
    else:
        default_is_mydriatic = False
    return {
        "allow_mydriatic": allow_mydriatic,
        "allow_non_mydriatic": allow_non_mydriatic,
        "default_is_mydriatic": default_is_mydriatic,
    }
