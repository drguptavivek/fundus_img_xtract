from __future__ import annotations

from flask import jsonify, render_template, request, url_for
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
    return render_template("glaucoma_ai/upload.html")


@bp.route("/form", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def upload_form_partial():
    with get_db_session() as db:
        upload_options = _load_upload_options(db)
    return render_template(
        "glaucoma_ai/_upload_form.html",
        upload_options=upload_options,
        mydriatic_options=_mydriatic_options(upload_options),
    )


@bp.route("/recent", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def recent_results_partial():
    with get_db_session() as db:
        limit = _query_int("limit", default=20, minimum=1, maximum=100)
        offset = _query_int("offset", default=0, minimum=0, maximum=10000)
        page_items = _load_web_recent_uploads(db, limit=limit + 1, offset=offset)
        recent_uploads = page_items[:limit]
    return render_template(
        "glaucoma_ai/_recent_results.html",
        recent_uploads=recent_uploads,
        pagination=_pagination(limit=limit, offset=offset, has_next=len(page_items) > limit),
    )


@bp.route("/workspace", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def workspace_partial():
    with get_db_session() as db:
        page_items = _load_web_recent_uploads(db, limit=21, offset=0)
        recent_uploads = page_items[:20]
    return render_template(
        "glaucoma_ai/_workspace.html",
        results=None,
        recent_uploads=recent_uploads,
        pagination=_pagination(limit=20, offset=0, has_next=len(page_items) > 20),
        messages=[],
    )


@bp.route("/recent/results", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def recent_results_json():
    limit = _query_int("limit", default=20, minimum=1, maximum=100)
    offset = _query_int("offset", default=0, minimum=0, maximum=10000)
    with get_db_session() as db:
        recent_uploads = load_user_glaucoma_ai_inference_updates(db, current_user.id, limit=limit, offset=offset)
    return jsonify({"items": recent_uploads, "limit": limit, "offset": offset, "count": len(recent_uploads)})


def _load_web_recent_uploads(db, *, limit: int, offset: int) -> list[dict]:
    items = load_user_glaucoma_ai_upload_results(
        db,
        current_user.id,
        limit=limit,
        offset=offset,
        external_urls=False,
        include_created_at_dt=True,
    )
    for item in items:
        image_uuid = item.get("image_uuid")
        if image_uuid:
            item["image_url"] = url_for("media._directImgFinalByUUID", uuid_str=image_uuid)
            item["thumbnail_url"] = url_for("media._directImgFinalThumbnailByUUID", uuid_str=image_uuid)
    return items


def _pagination(*, limit: int, offset: int, has_next: bool) -> dict:
    previous_offset = max(0, offset - limit)
    next_offset = offset + limit
    return {
        "limit": limit,
        "offset": offset,
        "previous_offset": previous_offset,
        "has_previous": offset > 0,
        "next_offset": next_offset,
        "has_next": has_next,
        "page_number": (offset // limit) + 1,
    }


def _query_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


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
