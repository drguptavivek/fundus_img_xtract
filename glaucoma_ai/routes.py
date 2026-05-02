from __future__ import annotations

from flask import jsonify, render_template, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from api.glaucoma_ai import load_user_glaucoma_ai_inference_updates, load_user_glaucoma_ai_upload_results
from services.glaucoma_ai_upload import get_glaucoma_disease_id
from upload_profiles.service import (
    UPLOAD_KIND_DIRECT_IMAGE,
    filter_upload_options,
    get_user_upload_options_for_kind,
    restrict_upload_options_to_profiles,
)

from . import bp


@bp.route("/", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def index():
    with get_db_session() as db:
        upload_options = _load_upload_options(db)
        recent_uploads = _load_web_recent_uploads(db)
    return render_template(
        "glaucoma_ai/upload.html",
        upload_options=upload_options,
        mydriatic_options=_mydriatic_options(upload_options),
        results=None,
        recent_uploads=recent_uploads,
    )


@bp.route("/recent", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def recent_results_partial():
    with get_db_session() as db:
        recent_uploads = _load_web_recent_uploads(db)
    return render_template("glaucoma_ai/_recent_results.html", recent_uploads=recent_uploads)


@bp.route("/workspace", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def workspace_partial():
    with get_db_session() as db:
        recent_uploads = _load_web_recent_uploads(db)
    return render_template(
        "glaucoma_ai/_workspace.html",
        results=None,
        recent_uploads=recent_uploads,
        messages=[],
    )


@bp.route("/recent/results", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def recent_results_json():
    with get_db_session() as db:
        recent_uploads = load_user_glaucoma_ai_inference_updates(db, current_user.id, limit=20, offset=0)
    return jsonify({"items": recent_uploads})


def _load_web_recent_uploads(db) -> list[dict]:
    items = load_user_glaucoma_ai_upload_results(
        db,
        current_user.id,
        limit=20,
        offset=0,
        external_urls=False,
        include_created_at_dt=True,
    )
    for item in items:
        image_uuid = item.get("image_uuid")
        if image_uuid:
            item["image_url"] = url_for("media._directImgFinalByUUID", uuid_str=image_uuid)
            item["thumbnail_url"] = url_for("media._directImgFinalThumbnailByUUID", uuid_str=image_uuid)
    return items


def _load_upload_options(db):
    glaucoma_disease_id = get_glaucoma_disease_id(db)
    options = get_user_upload_options_for_kind(db, current_user.id, UPLOAD_KIND_DIRECT_IMAGE)
    options = filter_upload_options(db, options, disease_id=glaucoma_disease_id)
    profiles = [
        profile for profile in options.profiles
        if any(
            workflow.get("disease_id") == glaucoma_disease_id
            and workflow.get("upload_kind") == UPLOAD_KIND_DIRECT_IMAGE
            and workflow.get("active", True)
            for workflow in profile.get("ai_workflows", [])
        )
    ]
    return restrict_upload_options_to_profiles(options, profiles)


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
