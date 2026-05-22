"""JSON API routes for grading scheme administration."""
from __future__ import annotations

from typing import Any

from flask import jsonify, request

from auth.roles import roles_required
from grading_schemes import service as grading_scheme_service
from upload_profiles.admin_service import MutationResult

from . import api_bp


@api_bp.route("/grading-schemes", methods=["GET"])
@roles_required("admin")
def list_grading_schemes():
    return jsonify({"success": True, "grading_schemes": grading_scheme_service.list_grading_schemes()})


@api_bp.route("/grading-schemes", methods=["POST"])
@roles_required("admin")
def create_grading_scheme():
    return _json_result(grading_scheme_service.create_grading_scheme(_input_from_request()))


@api_bp.route("/grading-schemes/<int:scheme_id>", methods=["GET"])
@roles_required("admin")
def get_grading_scheme(scheme_id: int):
    return _json_result(grading_scheme_service.get_grading_scheme(scheme_id))


@api_bp.route("/grading-schemes/<int:scheme_id>", methods=["PATCH", "POST"])
@roles_required("admin")
def update_grading_scheme(scheme_id: int):
    return _json_result(grading_scheme_service.update_grading_scheme(scheme_id, _input_from_request()))


@api_bp.route("/grading-schemes/<int:scheme_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_grading_scheme(scheme_id: int):
    return _json_result(grading_scheme_service.delete_grading_scheme(scheme_id))


@api_bp.route("/grading-schemes/<int:scheme_id>/grades", methods=["POST"])
@roles_required("admin")
def create_grading_scheme_grade(scheme_id: int):
    return _json_result(grading_scheme_service.create_grade(scheme_id, _grade_input_from_request()))


@api_bp.route("/grading-schemes/<int:scheme_id>/grades/<int:grade_id>", methods=["PATCH", "POST"])
@roles_required("admin")
def update_grading_scheme_grade(scheme_id: int, grade_id: int):
    return _json_result(grading_scheme_service.update_grade(scheme_id, grade_id, _grade_input_from_request()))


@api_bp.route("/grading-schemes/<int:scheme_id>/grades/<int:grade_id>/activate", methods=["POST"])
@roles_required("admin")
def activate_grading_scheme_grade(scheme_id: int, grade_id: int):
    return _json_result(grading_scheme_service.set_grade_active(scheme_id, grade_id, True))


@api_bp.route("/grading-schemes/<int:scheme_id>/grades/<int:grade_id>/deactivate", methods=["POST"])
@roles_required("admin")
def deactivate_grading_scheme_grade(scheme_id: int, grade_id: int):
    return _json_result(grading_scheme_service.set_grade_active(scheme_id, grade_id, False))


def _input_from_request() -> grading_scheme_service.GradingSchemeInput:
    data = _request_data()
    return grading_scheme_service.GradingSchemeInput(
        name=str(data.get("name") or "").strip(),
        grading_scope=str(data.get("grading_scope") or "").strip(),
        parent_scheme_id=_optional_int(data.get("parent_scheme_id")),
    )


def _grade_input_from_request() -> grading_scheme_service.GradeInput:
    data = _request_data()
    return grading_scheme_service.GradeInput(
        impression=str(data.get("impression") or "").strip(),
        display_order=_int_value(data.get("display_order"), default=0),
        is_active=_bool_value(data.get("is_active"), default=True),
        guidelines=(str(data.get("guidelines")).strip() if data.get("guidelines") is not None else None) or None,
        features=_feature_inputs(data),
    )


def _feature_inputs(data: dict[str, Any]) -> list[grading_scheme_service.GradeFeatureInput]:
    raw_features = data.get("features")
    if isinstance(raw_features, list):
        features = []
        for index, item in enumerate(raw_features, start=1):
            if not isinstance(item, dict):
                continue
            features.append(
                grading_scheme_service.GradeFeatureInput(
                    sr_no=_int_value(item.get("sr_no"), default=index),
                    label=str(item.get("label") or "").strip(),
                )
            )
        return features
    labels = data.get("feature_label") or []
    orders = data.get("feature_sr_no") or []
    if not isinstance(labels, list):
        labels = [labels]
    if not isinstance(orders, list):
        orders = [orders]
    features = []
    for index, label in enumerate(labels, start=1):
        features.append(
            grading_scheme_service.GradeFeatureInput(
                sr_no=_int_value(orders[index - 1] if index - 1 < len(orders) else None, default=index),
                label=str(label or "").strip(),
            )
        )
    return features


def _request_data() -> dict[str, Any]:
    if request.is_json:
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}
    data = dict(request.form.items())
    data["feature_label"] = request.form.getlist("feature_label")
    data["feature_sr_no"] = request.form.getlist("feature_sr_no")
    return data


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _json_result(result: MutationResult):
    payload = {"success": result.success, "message": result.message}
    if not result.success:
        payload["error"] = result.message
    if result.payload:
        payload.update(result.payload)
    return jsonify(payload), result.status_code
