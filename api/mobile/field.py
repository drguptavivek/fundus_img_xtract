"""Field staff API: project-scoped encounter queue, AI status, and upstream fetch.

Thin transport only. Authorization, scoping, status resolution, caching, and the
fetch adapters all live in :mod:`field_workbench`.
"""
from __future__ import annotations

import logging

from flask import jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.decorators import token_auth_required
from db_transaction_manager import transaction_scope
from field_workbench import service as field_service
from field_workbench.exceptions import FieldError
from field_workbench.throttle import enforce_fetch_spacing
from models import EncounterSetImage, User
from utils.rate_limiter import rate_limit

from . import mobile_api_bp

logger = logging.getLogger("api.mobile.field")

# Per user, not per project or per source. The coalescing guard inside each
# adapter is what actually protects the upstream provider; these bound how often
# one person can ask.
FETCH_RATE_LIMITS = "2 per minute; 20 per hour"


def _actor(db) -> User | None:
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return None
    user = db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == user_id)
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


def _error(exc: FieldError):
    payload = {"error": exc.code, "message": exc.message}
    response = jsonify(payload)
    response.status_code = exc.status_code
    retry_after = getattr(exc, "retry_after", None)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return response


def _unauthenticated():
    return jsonify({"error": "invalid_token", "message": "Invalid access token"}), 401


@mobile_api_bp.route("/field/projects", methods=["GET"])
@token_auth_required
def field_projects():
    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        projects = field_service.list_projects(db, user=user)
        return jsonify({"projects": [project.to_dict() for project in projects]})


@mobile_api_bp.route("/field/projects/<int:project_id>/encounter-dates", methods=["GET"])
@token_auth_required
def field_encounter_dates(project_id: int):
    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            dates = field_service.list_encounter_dates(db, user=user, project_id=project_id)
        except FieldError as exc:
            return _error(exc)
        return jsonify({"dates": [item.to_dict() for item in dates]})


@mobile_api_bp.route("/field/projects/<int:project_id>/encounters", methods=["GET"])
@token_auth_required
def field_encounters(project_id: int):
    date_value = (request.args.get("date") or "").strip()
    if not date_value:
        return jsonify({"error": "date_required", "message": "A date=YYYY-MM-DD query parameter is required."}), 400
    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            rows = field_service.list_daily_encounters(
                db, user=user, project_id=project_id, date_value=date_value
            )
        except FieldError as exc:
            return _error(exc)
        return jsonify({"date": date_value, "encounters": rows})


@mobile_api_bp.route("/field/encounters/<encounter_uuid>", methods=["GET"])
@token_auth_required
def field_encounter_detail(encounter_uuid: str):
    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            return jsonify(
                field_service.get_encounter_detail(db, user=user, encounter_uuid=encounter_uuid)
            )
        except FieldError as exc:
            return _error(exc)


@mobile_api_bp.route("/field/encounters/<encounter_uuid>/inference", methods=["POST"])
@token_auth_required
def field_request_inference(encounter_uuid: str):
    payload = request.get_json(silent=True) or {}
    workflows = payload.get("workflows") or []
    if not isinstance(workflows, list):
        return jsonify({"error": "invalid_workflows", "message": "workflows must be a list."}), 400
    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            result = field_service.request_inference(
                db,
                user=user,
                encounter_uuid=encounter_uuid,
                workflows=[str(item) for item in workflows],
                remote_addr=request.remote_addr,
            )
        except FieldError as exc:
            return _error(exc)
        queued = any(item.get("queued") for item in result["workflows"].values())
        return jsonify(result), 202 if queued else 200


@mobile_api_bp.route("/field/projects/<int:project_id>/fetch", methods=["GET"])
@token_auth_required
def field_fetch_status(project_id: int):
    source = (request.args.get("source") or "").strip() or None
    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            return jsonify(
                {"sources": field_service.get_fetch_status(db, user=user, project_id=project_id, source=source)}
            )
        except FieldError as exc:
            return _error(exc)


@mobile_api_bp.route("/field/projects/<int:project_id>/fetch", methods=["POST"])
@token_auth_required
@rate_limit(FETCH_RATE_LIMITS, methods=["POST"])
def field_queue_fetch(project_id: int):
    return _fetch_action(project_id, retry=False)


@mobile_api_bp.route("/field/projects/<int:project_id>/fetch/retry", methods=["POST"])
@token_auth_required
@rate_limit(FETCH_RATE_LIMITS, methods=["POST"])
def field_retry_fetch(project_id: int):
    return _fetch_action(project_id, retry=True)


def _fetch_action(project_id: int, *, retry: bool):
    payload = request.get_json(silent=True) or {}
    source = (payload.get("source") or request.args.get("source") or "remidio").strip()
    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            # The limiter expresses rates, not spacing, so the minimum gap
            # between one user's requests is enforced separately.
            enforce_fetch_spacing(user.id)
            action = field_service.retry_fetch if retry else field_service.queue_fetch
            status = action(
                db,
                user=user,
                project_id=project_id,
                source=source,
                remote_addr=request.remote_addr,
            )
        except FieldError as exc:
            return _error(exc)
        return jsonify(status), 202


@mobile_api_bp.route(
    "/field/encounters/<encounter_uuid>/images/<image_uuid>/thumbnail", methods=["GET"]
)
@token_auth_required
def field_encounter_image_thumbnail(encounter_uuid: str, image_uuid: str):
    return _serve_encounter_image(encounter_uuid, image_uuid, thumbnail=True)


@mobile_api_bp.route("/field/encounters/<encounter_uuid>/images/<image_uuid>", methods=["GET"])
@token_auth_required
def field_encounter_image(encounter_uuid: str, image_uuid: str):
    return _serve_encounter_image(encounter_uuid, image_uuid, thumbnail=False)


def _serve_encounter_image(encounter_uuid: str, image_uuid: str, *, thumbnail: bool):
    """Serve encounter imagery to a bearer-token client.

    Field scope is checked first, then the central media authorizer resolves and
    authorizes the object; its result is handed to the shared serving helper as
    ``preauthorized`` so this route does not fork media authorization.
    """
    from media.authorization import (
        MediaAccessDenied,
        MediaResolutionError,
        MediaSourceType,
        authorize_media_source,
    )
    from utils.utilsImgServe import encounterSetImageByUUID, encounterSetImageThumbnailByUUID

    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            encounter, _ = field_service._load_encounter(db, user=user, encounter_uuid=encounter_uuid)
        except FieldError as exc:
            return _error(exc)

        image = db.execute(
            select(EncounterSetImage).where(
                EncounterSetImage.uuid == image_uuid,
                EncounterSetImage.patient_encounter_id == encounter.id,
            )
        ).scalar_one_or_none()
        if image is None:
            return jsonify({"error": "not_found", "message": "Image not found."}), 404

        try:
            authorized = authorize_media_source(
                db,
                user=user,
                media_uuid=image_uuid,
                action="media.thumbnail.view" if thumbnail else "media.image.view",
                expected_sources=frozenset({MediaSourceType.ENCOUNTER_SET_IMAGE}),
            )
        except (MediaResolutionError, MediaAccessDenied):
            return jsonify({"error": "not_found", "message": "Image not found."}), 404

    if thumbnail:
        return encounterSetImageThumbnailByUUID(image_uuid, preauthorized=authorized)
    return encounterSetImageByUUID(image_uuid, preauthorized=authorized)


@mobile_api_bp.route("/field/encounters/<encounter_uuid>/report", methods=["GET"])
@token_auth_required
def field_encounter_report(encounter_uuid: str):
    """Serve the Remidio AI report PDF.

    Deliberately not gated on OCR: the PDF is readable the moment it lands, and
    making field staff wait for text extraction would withhold a report they
    could already open.
    """
    from flask import send_file

    from encounter_sets.models import EncounterSetAttachment as Attachment

    with transaction_scope() as db:
        user = _actor(db)
        if user is None:
            return _unauthenticated()
        try:
            encounter, _ = field_service._load_encounter(db, user=user, encounter_uuid=encounter_uuid)
        except FieldError as exc:
            return _error(exc)

        attachment = None
        for row in encounter.encounter_set_attachments or []:
            if row.asset_kind in {"pdf", "document", "document_image"} or row.mime_type == "application/pdf":
                attachment = row
                break
        if attachment is None:
            return jsonify({"error": "not_found", "message": "No report is available."}), 404

        path = _attachment_path(attachment)
        if path is None or not path.exists():
            return jsonify({"error": "not_found", "message": "No report is available."}), 404
        return send_file(path, mimetype="application/pdf", as_attachment=False)


def _attachment_path(attachment):
    from pathlib import Path

    from models import BASE_DIR

    folder = getattr(attachment, "folder_rel", None)
    filename = getattr(attachment, "stored_filename", None) or getattr(
        attachment, "original_filename", None
    )
    if not folder or not filename:
        return None
    return Path(BASE_DIR) / "encounter_sets" / folder / filename
