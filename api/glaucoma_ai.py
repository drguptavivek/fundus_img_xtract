from __future__ import annotations

import mimetypes
from typing import Any

from flask import current_app, jsonify, render_template, request, send_file, url_for
from flask_login import current_user
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import selectinload

from auth.decorators import token_auth_required
from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from media.authorization import (
    IMAGE_SOURCE_TYPES,
    MediaAccessDenied,
    MediaResolutionError,
    authorize_media_source,
)
from models import AIInferenceRun, DirectImageUpload, DirectImageVerify, Grade, GradingTask, Job, JobItem, User
from services.glaucoma_ai_upload import (
    GLAUCOMA_AI_UPLOAD_MARKER_REMARKS,
    GlaucomaAIUploadSelection,
    get_glaucoma_disease_id,
    process_glaucoma_ai_uploads,
)
from utils.fileUtils import abs_from_parts, get_thumbnail_path_direct
from utils.image_processing import generate_thumbnail, get_thumbnail_filename
from utils.log_sanitize import sanitize_log_value
from upload_profiles.service import UploadProfileError

from . import api_bp


ALLOWED_GLAUCOMA_AI_ROLES = {"admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader"}


@api_bp.route("/glaucoma-ai/uploads/recent", methods=["GET"])
@token_auth_required
def list_recent_glaucoma_ai_uploads():
    auth_error = _validate_glaucoma_ai_api_auth()
    if auth_error is not None:
        return auth_error
    user_id = getattr(request, "mobile_auth", {}).get("user_id")
    limit = _query_int("limit", default=20, minimum=1, maximum=100)
    offset = _query_int("offset", default=0, minimum=0, maximum=10000)

    with transaction_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        items = load_user_glaucoma_ai_upload_results(db, user_id, limit=limit, offset=offset, external_urls=True)

    return jsonify({"items": items, "limit": limit, "offset": offset, "count": len(items)})


@api_bp.route("/glaucoma-ai/uploads/recent/results", methods=["GET"])
@token_auth_required
def list_recent_glaucoma_ai_upload_results():
    auth_error = _validate_glaucoma_ai_api_auth()
    if auth_error is not None:
        return auth_error
    user_id = getattr(request, "mobile_auth", {}).get("user_id")
    limit = _query_int("limit", default=20, minimum=1, maximum=100)
    offset = _query_int("offset", default=0, minimum=0, maximum=10000)

    with transaction_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        items = load_user_glaucoma_ai_inference_updates(db, user_id, limit=limit, offset=offset)

    return jsonify({"items": items, "limit": limit, "offset": offset, "count": len(items)})


@api_bp.route("/glaucoma-ai/uploads/<string:uuid_str>/result", methods=["GET"])
@token_auth_required
def get_glaucoma_ai_upload_result(uuid_str: str):
    auth_error = _validate_glaucoma_ai_api_auth()
    if auth_error is not None:
        return auth_error
    user_id = getattr(request, "mobile_auth", {}).get("user_id")

    with transaction_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        glaucoma_disease_id = get_glaucoma_disease_id(db)
        upload = (
            db.execute(
                select(DirectImageUpload)
                .options(
                    selectinload(DirectImageUpload.project),
                    selectinload(DirectImageUpload.hospital),
                    selectinload(DirectImageUpload.lab_unit),
                    selectinload(DirectImageUpload.camera),
                    selectinload(DirectImageUpload.area),
                    selectinload(DirectImageUpload.disease),
                )
                .where(DirectImageUpload.uuid == uuid_str)
                .where(DirectImageUpload.uploader_id == user_id)
                .where(DirectImageUpload.disease_id == glaucoma_disease_id)
                .where(_glaucoma_ai_upload_visible_clause(user_id))
            )
            .scalar_one_or_none()
        )
        if upload is None:
            return jsonify({"error": "Upload not found"}), 404
        task_map = _load_glaucoma_task_map(db, [upload.id], glaucoma_disease_id)
        payload = _serialize_upload_result(upload, task_map.get(upload.id), include_image_url=True)

    return jsonify(payload)


@api_bp.route("/glaucoma-ai/uploads", methods=["POST"])
@token_auth_required
def create_glaucoma_ai_upload():
    auth_error = _validate_glaucoma_ai_api_auth()
    if auth_error is not None:
        return auth_error
    user_id = getattr(request, "mobile_auth", {}).get("user_id")

    try:
        selection = GlaucomaAIUploadSelection(
            project_id=_form_int("project_id"),
            lab_unit_id=_form_int("lab_unit_id"),
            camera_id=_form_int("camera_id"),
            area_id=_form_int("area_id"),
            is_mydriatic=_form_bool("is_mydriatic"),
            profile_id=_form_optional_int("profile_id"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    with transaction_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        username = user.username

    try:
        result = process_glaucoma_ai_uploads(
            files=request.files.getlist("files"),
            user_id=user_id,
            username=username,
            remote_addr=request.remote_addr,
            selection=selection,
            request_url_builder=lambda image_uuid: url_for(
                "fundus_api.get_glaucoma_ai_upload_image",
                uuid_str=image_uuid,
                _external=True,
            ),
            thumbnail_url_builder=lambda image_uuid: url_for(
                "fundus_api.get_glaucoma_ai_upload_thumbnail",
                uuid_str=image_uuid,
                _external=True,
            ),
            app=current_app._get_current_object(),
        )
    except UploadProfileError as exc:
        current_app.logger.warning(
            "JWT glaucoma AI upload rejected user=%s code=%s",
            sanitize_log_value(user_id),
            sanitize_log_value(exc.code),
        )
        return jsonify({"error": exc.message, "code": exc.code}), 400

    status_code = 201 if result.success_count else 400
    return jsonify(
        {
            "success": result.success_count > 0,
            "success_count": result.success_count,
            "error_count": result.error_count,
            "items": [_serialize_item(item) for item in result.items],
        }
    ), status_code


@api_bp.route("/glaucoma-ai/uploads/web", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist", "fileUploader")
def create_glaucoma_ai_upload_web():
    """Session-auth HTMX endpoint for the browser upload page."""
    try:
        selection = GlaucomaAIUploadSelection(
            project_id=_form_int("project_id"),
            lab_unit_id=_form_int("lab_unit_id"),
            camera_id=_form_int("camera_id"),
            area_id=_form_int("area_id"),
            is_mydriatic=_form_bool("is_mydriatic"),
            profile_id=_form_optional_int("profile_id"),
        )
    except ValueError as exc:
        return _web_upload_response(str(exc), "danger", None, status_code=400)

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
            "Web glaucoma AI upload rejected for user=%s code=%s",
            sanitize_log_value(current_user.id),
            sanitize_log_value(exc.code),
        )
        return _web_upload_response(exc.message, "danger", None, status_code=400)

    messages = []
    if result.success_count:
        messages.append(("success", f"Submitted {result.success_count} image(s) for AI inference. Human verification is still required before human grading."))
    if result.error_count:
        messages.append(("warning", f"{result.error_count} image(s) could not be processed."))

    if request.headers.get("HX-Request"):
        return _render_web_workspace(result=result, messages=messages)

    return jsonify(
        {
            "success": result.success_count > 0,
            "success_count": result.success_count,
            "error_count": result.error_count,
            "items": [_serialize_item(item) for item in result.items],
        }
    ), 201 if result.success_count else 400


@api_bp.route("/glaucoma-ai/uploads/<string:uuid_str>/image", methods=["GET"])
@token_auth_required
def get_glaucoma_ai_upload_image(uuid_str: str):
    auth_error = _validate_glaucoma_ai_api_auth()
    if auth_error is not None:
        return auth_error
    user_id = getattr(request, "mobile_auth", {}).get("user_id")

    with transaction_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        glaucoma_disease_id = get_glaucoma_disease_id(db)
        upload = (
            db.query(DirectImageUpload)
            .filter(DirectImageUpload.uuid == uuid_str)
            .filter(DirectImageUpload.uploader_id == user_id)
            .filter(DirectImageUpload.disease_id == glaucoma_disease_id)
            .filter(_glaucoma_ai_upload_visible_clause(user_id))
            .one_or_none()
        )
        if upload is None:
            return jsonify({"error": "Image not found"}), 404
        try:
            authorize_media_source(
                db,
                user=user,
                media_uuid=uuid_str,
                action="media.image.view",
                expected_sources=IMAGE_SOURCE_TYPES,
            )
        except (MediaResolutionError, MediaAccessDenied):
            return jsonify({"error": "Image not found"}), 404
        filename = upload.edited_filename or upload.filename
        kind = "edited" if upload.edited_filename else "orig"
        path = abs_from_parts(upload.folder_rel, filename, kind)

    mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = send_file(path, mimetype=mimetype, as_attachment=False, conditional=True)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "private, max-age=600")
    return response


@api_bp.route("/glaucoma-ai/uploads/<string:uuid_str>/thumbnail", methods=["GET"])
@token_auth_required
def get_glaucoma_ai_upload_thumbnail(uuid_str: str):
    auth_error = _validate_glaucoma_ai_api_auth()
    if auth_error is not None:
        return auth_error
    user_id = getattr(request, "mobile_auth", {}).get("user_id")

    with transaction_scope() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        glaucoma_disease_id = get_glaucoma_disease_id(db)
        upload = (
            db.query(DirectImageUpload)
            .filter(DirectImageUpload.uuid == uuid_str)
            .filter(DirectImageUpload.uploader_id == user_id)
            .filter(DirectImageUpload.disease_id == glaucoma_disease_id)
            .filter(_glaucoma_ai_upload_visible_clause(user_id))
            .one_or_none()
        )
        if upload is None:
            return jsonify({"error": "Image not found"}), 404
        try:
            authorize_media_source(
                db,
                user=user,
                media_uuid=uuid_str,
                action="media.thumbnail.view",
                expected_sources=IMAGE_SOURCE_TYPES,
            )
        except (MediaResolutionError, MediaAccessDenied):
            return jsonify({"error": "Image not found"}), 404
        try:
            path = _resolve_or_create_thumbnail(upload)
        except FileNotFoundError:
            return jsonify({"error": "Thumbnail not found"}), 404

    mimetype = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    response = send_file(path, mimetype=mimetype, as_attachment=False, conditional=True)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "private, max-age=600")
    response.headers.setdefault("X-Thumbnail", "true")
    return response


def _validate_glaucoma_ai_api_auth():
    user_id = getattr(request, "mobile_auth", {}).get("user_id")
    roles = set((getattr(request, "mobile_claims", {}) or {}).get("roles") or [])
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401
    if not roles.intersection(ALLOWED_GLAUCOMA_AI_ROLES):
        return jsonify({"error": "Forbidden"}), 403
    return None


def _form_int(name: str) -> int:
    try:
        value = int(request.form.get(name, ""))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is required") from exc
    if value <= 0:
        raise ValueError(f"{name} is required")
    return value


def _form_optional_int(name: str) -> int | None:
    raw = request.form.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _form_bool(name: str) -> bool:
    value = (request.form.get(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _query_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _render_web_workspace(*, result=None, messages=None):
    with transaction_scope() as db:
        page_items = _load_web_recent_uploads(db, current_user.id, limit=21, offset=0)
        recent_uploads = page_items[:20]
    return render_template(
        "glaucoma_ai/_workspace.html",
        results=result,
        recent_uploads=recent_uploads,
        pagination={
            "limit": 20,
            "offset": 0,
            "previous_offset": 0,
            "has_previous": False,
            "next_offset": 20,
            "has_next": len(page_items) > 20,
            "page_number": 1,
        },
        messages=messages or [],
    )


def _web_upload_response(message: str, category: str, result, *, status_code: int):
    if request.headers.get("HX-Request"):
        return _render_web_workspace(result=result, messages=[(category, message)])
    return jsonify({"success": False, "error": message}), status_code


def _load_web_recent_uploads(db, user_id: int, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    items = load_user_glaucoma_ai_upload_results(
        db,
        user_id,
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


def _load_glaucoma_task_map(db, upload_ids: list[int], glaucoma_disease_id: int) -> dict[int, GradingTask]:
    if not upload_ids:
        return {}
    tasks = (
        db.execute(
            select(GradingTask)
            .options(
                selectinload(GradingTask.grades).selectinload(Grade.ai_model),
                selectinload(GradingTask.inference_runs).selectinload(AIInferenceRun.ai_model),
            )
            .where(GradingTask.direct_image_upload_id.in_(upload_ids))
            .where(GradingTask.disease_id == glaucoma_disease_id)
        )
        .scalars()
        .all()
    )
    return {task.direct_image_upload_id: task for task in tasks if task.direct_image_upload_id is not None}


def load_user_glaucoma_ai_upload_results(
    db,
    user_id: int,
    *,
    limit: int,
    offset: int = 0,
    external_urls: bool = False,
    include_created_at_dt: bool = False,
) -> list[dict[str, Any]]:
    glaucoma_disease_id = get_glaucoma_disease_id(db)
    uploads = (
        db.execute(
            select(DirectImageUpload)
            .options(
                selectinload(DirectImageUpload.project),
                selectinload(DirectImageUpload.hospital),
                selectinload(DirectImageUpload.lab_unit),
                selectinload(DirectImageUpload.camera),
                selectinload(DirectImageUpload.area),
                selectinload(DirectImageUpload.disease),
            )
            .where(DirectImageUpload.uploader_id == user_id)
            .where(DirectImageUpload.disease_id == glaucoma_disease_id)
            .where(_glaucoma_ai_upload_visible_clause(user_id))
            .order_by(DirectImageUpload.created_at.desc(), DirectImageUpload.id.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    task_map = _load_glaucoma_task_map(db, [upload.id for upload in uploads], glaucoma_disease_id)
    return [
        _serialize_upload_result(
            upload,
            task_map.get(upload.id),
            include_image_url=True,
            external_urls=external_urls,
            include_created_at_dt=include_created_at_dt,
        )
        for upload in uploads
    ]


def load_user_glaucoma_ai_inference_updates(
    db,
    user_id: int,
    *,
    limit: int,
    offset: int = 0,
) -> list[dict[str, Any]]:
    glaucoma_disease_id = get_glaucoma_disease_id(db)
    uploads = (
        db.execute(
            select(DirectImageUpload)
            .where(DirectImageUpload.uploader_id == user_id)
            .where(DirectImageUpload.disease_id == glaucoma_disease_id)
            .where(_glaucoma_ai_upload_visible_clause(user_id))
            .order_by(DirectImageUpload.created_at.desc(), DirectImageUpload.id.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    task_map = _load_glaucoma_task_map(db, [upload.id for upload in uploads], glaucoma_disease_id)
    return [_serialize_inference_update(upload, task_map.get(upload.id)) for upload in uploads]


def _serialize_upload_result(
    upload: DirectImageUpload,
    task: GradingTask | None,
    *,
    include_image_url: bool,
    external_urls: bool = True,
    include_created_at_dt: bool = False,
) -> dict[str, Any]:
    latest_run = _latest_inference_run(task)
    ai_grade = _latest_ai_grade(task)
    result = {
        "upload_id": upload.id,
        "image_uuid": upload.uuid,
        "filename": upload.filename,
        "original_filename": upload.original_filename,
        "created_at": upload.created_at.isoformat() if upload.created_at else None,
        "project": _id_name(upload.project, label_attr="title"),
        "hospital": _id_name(upload.hospital),
        "lab_unit": _id_name(upload.lab_unit),
        "camera": _id_name(upload.camera),
        "area": _id_name(upload.area),
        "disease": _id_name(upload.disease),
        "is_mydriatic": upload.is_mydriatic,
        "task_id": task.id if task else None,
        "task_uuid": task.uuid if task else None,
        "task_state": task.state if task else None,
        "image_url": (
            url_for("fundus_api.get_glaucoma_ai_upload_image", uuid_str=upload.uuid, _external=external_urls)
            if include_image_url
            else None
        ),
        "thumbnail_url": (
            url_for("fundus_api.get_glaucoma_ai_upload_thumbnail", uuid_str=upload.uuid, _external=external_urls)
            if include_image_url
            else None
        ),
        "result_url": url_for("fundus_api.get_glaucoma_ai_upload_result", uuid_str=upload.uuid, _external=external_urls),
        "inference": _serialize_inference_result(latest_run, ai_grade),
    }
    if include_created_at_dt:
        result["created_at_dt"] = upload.created_at
    return result


def _glaucoma_ai_upload_visible_clause(user_id: int):
    return or_(
        DirectImageUpload.verifications.any(
            DirectImageVerify.remarks.in_(GLAUCOMA_AI_UPLOAD_MARKER_REMARKS)
        ),
        exists(
            select(JobItem.id)
            .join(Job, Job.id == JobItem.job_id)
            .where(JobItem.source_type == "direct_image")
            .where(JobItem.source_id == DirectImageUpload.id)
            .where(Job.uploader_user_id == user_id)
            .where(Job.upload_type == "mobile direct image")
        ),
    )


def _serialize_inference_update(upload: DirectImageUpload, task: GradingTask | None) -> dict[str, Any]:
    latest_run = _latest_inference_run(task)
    ai_grade = _latest_ai_grade(task)
    return {
        "upload_id": upload.id,
        "image_uuid": upload.uuid,
        "filename": upload.filename,
        "task_id": task.id if task else None,
        "task_uuid": task.uuid if task else None,
        "task_state": task.state if task else None,
        "inference": _serialize_inference_result(latest_run, ai_grade),
    }


def _latest_inference_run(task: GradingTask | None) -> AIInferenceRun | None:
    if task is None:
        return None
    runs = sorted(task.inference_runs or [], key=lambda run: run.created_at, reverse=True)
    return runs[0] if runs else None


def _latest_ai_grade(task: GradingTask | None) -> Grade | None:
    if task is None:
        return None
    grades = [grade for grade in (task.grades or []) if grade.role_slot == "ai"]
    grades.sort(key=lambda grade: grade.created_at, reverse=True)
    return grades[0] if grades else None


def _serialize_inference_result(run: AIInferenceRun | None, grade: Grade | None) -> dict[str, Any]:
    execute_payload = run.execute_response_json if run and isinstance(run.execute_response_json, dict) else {}
    result_row = _first_result_row(execute_payload)
    return {
        "status": run.status if run else ("success" if grade else "pending"),
        "message": run.error_message if run and run.status == "failed" else None,
        "ai_model_id": (run.ai_model_id if run else None) or (grade.ai_model_id if grade else None),
        "ai_model_name": (
            run.ai_model.name if run and run.ai_model else None
        )
        or (grade.ai_model_name if grade else None),
        "ai_model_version": (
            run.ai_model.version if run and run.ai_model else None
        )
        or (grade.ai_model_version if grade else None),
        "inference_run_id": run.id if run else None,
        "grade_id": grade.id if grade else None,
        "prediction_id": (run.prediction_id if run else None) or execute_payload.get("prediction_id"),
        "confidence": _extract_confidence(result_row, grade),
        "predicted_class": result_row.get("predicted_class"),
        "predicted_class_name": result_row.get("predicted_class_name"),
        "prediction": result_row.get("prediction"),
        "grade_impression": grade.grade_name if grade else None,
        "error_code": run.error_code if run else None,
        "started_at": run.started_at.isoformat() if run and run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run and run.finished_at else None,
    }


def _first_result_row(execute_payload: dict[str, Any]) -> dict[str, Any]:
    results = execute_payload.get("results") or []
    return results[0] if results and isinstance(results[0], dict) else {}


def _extract_confidence(result_row: dict[str, Any], grade: Grade | None) -> float | None:
    value = result_row.get("model_score")
    if value is None:
        value = result_row.get("confidence")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if grade and grade.comment:
        marker = "AI probability:"
        for line in grade.comment.splitlines():
            if marker in line:
                try:
                    return float(line.split(marker, 1)[1].strip())
                except (TypeError, ValueError):
                    return None
    return None


def _id_name(obj, *, label_attr: str = "name") -> dict[str, Any] | None:
    if obj is None:
        return None
    return {"id": obj.id, "name": getattr(obj, label_attr, None)}


def _resolve_or_create_thumbnail(upload: DirectImageUpload):
    if upload.edited_filename:
        thumbnail_path = get_thumbnail_path_direct(upload.folder_rel, upload.edited_filename, "edited")
        if thumbnail_path.exists():
            return thumbnail_path
        source_path = abs_from_parts(upload.folder_rel, upload.edited_filename, "edited")
        if source_path.exists() and generate_thumbnail(source_path, thumbnail_path):
            upload.edited_thumbnail_filename = get_thumbnail_filename(upload.edited_filename)
            return thumbnail_path

    if upload.filename:
        thumbnail_path = get_thumbnail_path_direct(upload.folder_rel, upload.filename, "orig")
        if thumbnail_path.exists():
            return thumbnail_path
        source_path = abs_from_parts(upload.folder_rel, upload.filename, "orig")
        if source_path.exists() and generate_thumbnail(source_path, thumbnail_path):
            upload.thumbnail_filename = get_thumbnail_filename(upload.filename)
            return thumbnail_path

    raise FileNotFoundError("Thumbnail source image not found")


def _serialize_item(item):
    inference = item.inference
    return {
        "filename": item.filename,
        "status": item.status,
        "message": item.message,
        "upload_id": item.upload_id,
        "image_uuid": item.image_uuid,
        "task_id": item.task_id,
        "task_uuid": item.task_uuid,
        "job_token": item.job_token,
        "image_url": item.image_url,
        "thumbnail_url": item.thumbnail_url,
        "inference": None
        if inference is None
        else {
            "status": inference.status,
            "message": inference.message,
            "ai_model_id": inference.ai_model_id,
            "inference_run_id": inference.inference_run_id,
            "grade_id": inference.grade_id,
            "prediction_id": inference.prediction_id,
            "confidence": inference.confidence,
            "predicted_class": inference.predicted_class,
            "predicted_class_name": inference.predicted_class_name,
            "grade_impression": inference.grade_impression,
            "reused_existing_grade": inference.reused_existing_grade,
            "error_code": inference.error_code,
        },
    }
