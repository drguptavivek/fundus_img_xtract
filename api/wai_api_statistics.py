"""JSON APIs for WAI API statistics."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from flask import jsonify, request, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from services.wai_api_statistics import (
    WaiStatsFilters,
    build_filters,
    get_encounter_results,
    get_filter_options,
    get_image_results,
    get_summary,
    retry_failed_inference_run,
)
from utils.date_utils import parse_date_yyyy_mm_dd

from . import api_bp


def _date_arg(name: str) -> date | None:
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    return parse_date_yyyy_mm_dd(raw)


def _filters_from_request() -> WaiStatsFilters:
    return build_filters(
        disease_ids=request.args.getlist("disease_id"),
        project_ids=request.args.getlist("project_id"),
        ai_model_ids=request.args.getlist("ai_model_id"),
        result_types=request.args.getlist("result_type"),
        inference_statuses=request.args.getlist("inference_status"),
        capture_start=_date_arg("capture_start"),
        capture_end=_date_arg("capture_end"),
        inference_start=_date_arg("inference_start"),
        inference_end=_date_arg("inference_end"),
    )


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _image_urls(row: dict[str, Any]) -> dict[str, Any]:
    image_uuid = row.get("image_uuid")
    image_source = row.get("image_source")
    encounter_id = row.get("normalized_patient_encounter_id")
    if image_uuid and image_source == "direct_image":
        row["thumbnail_url"] = url_for("media._directImgFinalThumbnailByUUID", uuid_str=image_uuid)
        row["viewer_url"] = url_for("fundus_api.encounter_viewer_image", image_uuid=image_uuid)
    elif image_uuid and image_source == "encounter_set_image":
        row["thumbnail_url"] = url_for("media._encounterSetImageThumbnailByUUID", uuid_str=image_uuid)
        row["viewer_url"] = url_for("fundus_api.encounter_viewer_encounter", encounter_id=encounter_id) if encounter_id else None
    elif image_uuid:
        row["thumbnail_url"] = url_for("media._imgForGradingByUUID", uuid_str=image_uuid)
        row["viewer_url"] = url_for("fundus_api.encounter_viewer_encounter", encounter_id=encounter_id) if encounter_id else None
    else:
        row["thumbnail_url"] = None
        row["viewer_url"] = url_for("fundus_api.encounter_viewer_encounter", encounter_id=encounter_id) if encounter_id else None
    row["retry_url"] = (
        url_for("fundus_api.wai_api_statistics_retry", inference_run_id=row["inference_run_id"])
        if row.get("inference_status") == "failed"
        else None
    )
    return row


def _encounter_urls(row: dict[str, Any]) -> dict[str, Any]:
    encounter_id = row.get("normalized_patient_encounter_id")
    row["viewer_url"] = url_for("fundus_api.encounter_viewer_encounter", encounter_id=encounter_id) if encounter_id else None
    for item in row.get("image_results") or []:
        item["retry_url"] = (
            url_for("fundus_api.wai_api_statistics_retry", inference_run_id=item["inference_run_id"])
            if item.get("status") == "failed" and item.get("inference_run_id")
            else None
        )
    return row


@api_bp.route("/analytics/wai-api-statistics/options", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def wai_api_statistics_options():
    with get_db_session() as db:
        payload = get_filter_options(db, current_user)
    return jsonify(_serialize(payload))


@api_bp.route("/analytics/wai-api-statistics/summary", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def wai_api_statistics_summary():
    with get_db_session() as db:
        payload = get_summary(db, current_user, _filters_from_request())
    return jsonify(_serialize(payload))


@api_bp.route("/analytics/wai-api-statistics/images", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def wai_api_statistics_images():
    page = request.args.get("page", default=1, type=int)
    page_size = request.args.get("page_size", default=25, type=int)
    with get_db_session() as db:
        payload = get_image_results(db, current_user, _filters_from_request(), page=page, page_size=page_size)
    payload["rows"] = [_image_urls(row) for row in payload["rows"]]
    return jsonify(_serialize(payload))


@api_bp.route("/analytics/wai-api-statistics/encounters", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def wai_api_statistics_encounters():
    page = request.args.get("page", default=1, type=int)
    page_size = request.args.get("page_size", default=25, type=int)
    with get_db_session() as db:
        payload = get_encounter_results(db, current_user, _filters_from_request(), page=page, page_size=page_size)
    payload["rows"] = [_encounter_urls(row) for row in payload["rows"]]
    return jsonify(_serialize(payload))


@api_bp.route("/analytics/wai-api-statistics/inference-runs/<int:inference_run_id>/retry", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def wai_api_statistics_retry(inference_run_id: int):
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    remote_addr = xff or (request.remote_addr or "-")
    try:
        with get_db_session() as db:
            payload = retry_failed_inference_run(
                db,
                current_user,
                inference_run_id=inference_run_id,
                remote_addr=remote_addr,
            )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    payload["job_url"] = url_for(
        "remidio_api_uploads.encounter_set_wadhwani_inference_job",
        job_token=payload["job_token"],
    )
    return jsonify({"success": True, **_serialize(payload)})
