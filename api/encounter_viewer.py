"""JSON and HTMX transport for the unified encounter evidence viewer."""

from __future__ import annotations

from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required

from db_transaction_manager import get_db_session
from encounter_viewer import (
    ViewerAccessDenied,
    ViewerNotFound,
    build_encounter_viewer,
    build_image_viewer,
)

from . import api_bp


def _response(dto):
    presentation = (request.args.get("presentation") or "compact").strip().lower()
    if presentation not in {"compact", "fullscreen"}:
        return jsonify({"error": "invalid_presentation"}), 400
    selected_uuid = (request.args.get("selected_image_uuid") or "").strip() or None
    if selected_uuid and selected_uuid not in {image.uuid for image in dto.images}:
        return jsonify({"error": "selected_image_not_found"}), 400
    if request.headers.get("HX-Request") == "true":
        response = render_template(
            "encounter_viewer/_viewer.html",
            viewer=dto,
            selected_image_uuid=selected_uuid,
            autolaunch=presentation == "fullscreen",
        )
        return response, 200, {"Cache-Control": "private, no-store", "Vary": "HX-Request"}
    response = jsonify(dto.to_dict())
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "HX-Request"
    return response


@api_bp.route("/encounter-viewer/encounters/<int:encounter_id>", methods=["GET"])
@login_required
def encounter_viewer_encounter(encounter_id: int):
    try:
        with get_db_session() as db:
            dto = build_encounter_viewer(db, user=current_user, encounter_id=encounter_id)
    except (ViewerNotFound, ViewerAccessDenied):
        abort(404)
    return _response(dto)


@api_bp.route("/encounter-viewer/images/<string:image_uuid>", methods=["GET"])
@login_required
def encounter_viewer_image(image_uuid: str):
    try:
        with get_db_session() as db:
            dto = build_image_viewer(db, user=current_user, image_uuid=image_uuid)
    except (ViewerNotFound, ViewerAccessDenied):
        abort(404)
    return _response(dto)
