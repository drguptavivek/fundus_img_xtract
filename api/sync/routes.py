"""Desktop project mirror API (``Authorization: Bearer pds_...``).

Every request re-authenticates the sync credential and re-derives the grant's
Lab Unit scope; nothing here accepts a browser session. See
docs/API/project_sync/README.md.
"""
from __future__ import annotations

import logging
from functools import wraps

from flask import current_app, g, jsonify, make_response, request, send_file

from auth.credentials import credential_authenticated
from auth.utils import get_client_ip
from db_transaction_manager import transaction_scope
from media.delivery import deliver_media
from project_sync import exports as sync_exports
from project_sync.dto import RequestMeta
from project_sync.exceptions import ProjectSyncError, ProjectSyncValidationError
from project_sync.inventory import (
    MAX_DIRECT_PAGE,
    MAX_ENCOUNTER_PAGE,
    VARIANTS,
    authorize_sync_media,
    build_sidecars,
    describe_context,
    list_direct_images,
    list_encounters,
    parse_page,
)
from project_sync.service import authenticate_credential
from project_sync.throttle import ProjectSyncBusy, acquire_slot, release_slot
from utils.log_sanitize import sanitize_log_value
from utils.rate_limiter import rate_limit

from . import project_sync_api_bp

logger = logging.getLogger("project_sync.api")


def _error(exc: ProjectSyncError):
    response = jsonify({"error": exc.code, "message": exc.message})
    response.status_code = exc.status_code
    response.headers["Cache-Control"] = "no-store"
    return response


def sync_credential_required(view):
    """Authenticate the bearer sync credential and expose ``g.project_sync``."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        credential = header[7:].strip() if header.startswith("Bearer ") else ""
        meta = RequestMeta(ip_address=get_client_ip(), user_agent=request.headers.get("User-Agent", ""))
        try:
            with transaction_scope() as db:
                g.project_sync = authenticate_credential(db, credential=credential, meta=meta)
        except ProjectSyncError as exc:
            if exc.status_code == 401:
                logger.warning("project_sync rejected credential ip=%s", sanitize_log_value(meta.ip_address))
            return _error(exc)
        try:
            slot = acquire_slot()
        except ProjectSyncBusy as exc:
            response = _error(exc)
            response.headers["Retry-After"] = str(exc.retry_after)
            return response
        try:
            response = make_response(view(*args, **kwargs))
        except BaseException:
            release_slot(slot)
            raise
        # Hold the slot until a streamed file body has been fully sent.
        response.call_on_close(lambda: release_slot(slot))
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    return credential_authenticated(wrapped)


def _json(payload):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@project_sync_api_bp.route("/whoami", methods=["GET"])
@rate_limit("60 per minute")
@sync_credential_required
def whoami():
    with transaction_scope() as db:
        return _json(describe_context(db, g.project_sync))


@project_sync_api_bp.route("/encounters", methods=["GET"])
@rate_limit("600 per minute")
@sync_credential_required
def encounters():
    try:
        after_id, limit = parse_page(request.args.get("after_id"), request.args.get("limit"), maximum=MAX_ENCOUNTER_PAGE)
        with transaction_scope() as db:
            return _json(list_encounters(db, g.project_sync, after_id=after_id, limit=limit))
    except ProjectSyncError as exc:
        return _error(exc)


@project_sync_api_bp.route("/direct-images", methods=["GET"])
@rate_limit("600 per minute")
@sync_credential_required
def direct_images():
    try:
        after_id, limit = parse_page(request.args.get("after_id"), request.args.get("limit"), maximum=MAX_DIRECT_PAGE)
        with transaction_scope() as db:
            return _json(list_direct_images(db, g.project_sync, after_id=after_id, limit=limit))
    except ProjectSyncError as exc:
        return _error(exc)


@project_sync_api_bp.route("/sidecars", methods=["POST"])
@rate_limit("300 per minute")
@sync_credential_required
def sidecars():
    payload = request.get_json(silent=True)
    try:
        if not isinstance(payload, dict):
            raise ProjectSyncValidationError("Body must be a JSON object with 'encounters' and/or 'images'.")
        with transaction_scope() as db:
            return _json(
                build_sidecars(
                    db, g.project_sync,
                    encounter_uuids=payload.get("encounters"),
                    image_uuids=payload.get("images"),
                )
            )
    except ProjectSyncError as exc:
        return _error(exc)


@project_sync_api_bp.route("/media/<media_uuid>", methods=["GET"])
@rate_limit("6000 per hour; 300 per minute")
@sync_credential_required
def media(media_uuid: str):
    variant = (request.args.get("variant") or "original").strip()
    try:
        if variant not in VARIANTS:
            raise ProjectSyncValidationError("variant must be 'original' or 'edited'.")
        with transaction_scope() as db:
            resource = authorize_sync_media(db, g.project_sync, media_uuid)
            logger.info(
                "project_sync media grant=%s uuid=%s variant=%s",
                sanitize_log_value(g.project_sync.grant_uuid),
                sanitize_log_value(media_uuid),
                sanitize_log_value(variant),
            )
            response = deliver_media(db, resource, variant=variant, exact_original=True)
    except ProjectSyncError as exc:
        return _error(exc)
    response.headers["Cache-Control"] = "no-store"
    return response


@project_sync_api_bp.route("/exports", methods=["POST"])
@rate_limit("6 per hour")
@sync_credential_required
def request_export():
    """Queue the project workbook on the Celery exports queue (202)."""
    try:
        with transaction_scope() as db:
            job = sync_exports.request_export(
                db, g.project_sync, app=current_app._get_current_object(), ip_address=get_client_ip()
            )
    except ProjectSyncError as exc:
        return _error(exc)
    response = _json({"export": job.to_dict()})
    response.status_code = 202
    return response


@project_sync_api_bp.route("/exports/latest", methods=["GET"])
@rate_limit("120 per hour")
@sync_credential_required
def latest_export():
    with transaction_scope() as db:
        job = sync_exports.latest_export(db, g.project_sync)
    return _json({"export": job.to_dict() if job else None})


@project_sync_api_bp.route("/exports/<job_token>/<filename>", methods=["GET"])
@rate_limit("60 per hour")
@sync_credential_required
def download_export(job_token: str, filename: str):
    try:
        with transaction_scope() as db:
            path = sync_exports.export_file(db, g.project_sync, token=job_token, filename=filename)
    except ProjectSyncError as exc:
        return _error(exc)
    return send_file(path, as_attachment=True, download_name=filename)
