"""REST API for scoped non-PII project review data."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from flask import current_app, jsonify, make_response, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from db_transaction_manager import transaction_scope
from project_review.exceptions import ProjectReviewNotFound
from project_review.service import (
    get_direct_image_verification,
    get_gradings,
    get_summary,
    get_uploads,
    list_projects,
    verify_direct_image,
)
from authz.project_access import project_capabilities
from job_store import db_create_job
from models import Job
from project_review.export_service import (
    EXPORT_DIR,
    authorized_project_export_labs,
    enqueue_project_export,
    project_export_history,
    project_export_preview,
    validate_export_request,
)
from werkzeug.utils import secure_filename

from . import api_bp


def _response(data):
    return jsonify({"success": True, "data": asdict(data) if not isinstance(data, tuple) else [asdict(row) for row in data]})


def _date_arg(name: str) -> date | None:
    value = request.args.get(name, "").strip()
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _project_export_request(project_id: int, actor_user_id: int, *, kind: str | None = None):
    payload = request.get_json(silent=True) or request.form or request.args
    return validate_export_request(
        project_id=project_id,
        actor_user_id=actor_user_id,
        kind=kind or str(payload.get("kind", "workbook")),
        date_from=date.fromisoformat(payload["date_from"]) if payload.get("date_from") else None,
        date_to=date.fromisoformat(payload["date_to"]) if payload.get("date_to") else None,
        grading_filter=str(payload.get("grading_filter", "any_graded")),
    )


@api_bp.route("/projects", methods=["GET"])
@login_required
def review_projects():
    with transaction_scope() as db:
        return _response(list_projects(db, user=current_user))


@api_bp.route("/projects/<int:project_id>/review/summary", methods=["GET"])
@login_required
def project_review_summary(project_id: int):
    try:
        with transaction_scope() as db:
            return _response(get_summary(db, user=current_user, project_id=project_id))
    except ProjectReviewNotFound as exc:
        return jsonify({"success": False, "error": str(exc)}), 404


@api_bp.route("/projects/<int:project_id>/review/uploads", methods=["GET"])
@login_required
def project_review_uploads(project_id: int):
    try:
        with transaction_scope() as db:
            data = get_uploads(
                db,
                user=current_user,
                project_id=project_id,
                page=request.args.get("page", 1, type=int),
                per_page=request.args.get("per_page", 100, type=int),
                status=request.args.get("status", "all"),
                lab_unit_id=request.args.get("lab_unit_id", type=int),
                date_from=_date_arg("date_from"),
                date_to=_date_arg("date_to"),
            )
            if request.headers.get("HX-Request") == "true":
                capabilities = project_capabilities(db, user=current_user, project_id=project_id)
                response = make_response(render_template(
                    "projects/_uploads_workspace.html", data=data, capabilities=capabilities
                ))
                response.headers["HX-Push-Url"] = url_for(
                    "projects.uploads", project_id=project_id, **request.args.to_dict()
                )
                return response
            return _response(data)
    except ProjectReviewNotFound as exc:
        return jsonify({"success": False, "error": str(exc)}), 404


@api_bp.route("/projects/<int:project_id>/direct-images/<uuid>/verification", methods=["GET", "POST"])
@login_required
def project_direct_image_verification(project_id: int, uuid):
    try:
        with transaction_scope() as db:
            error = None
            if request.method == "POST":
                try:
                    data = verify_direct_image(
                        db, user=current_user, project_id=project_id, uuid=str(uuid),
                        status=request.form.get("status", ""),
                        remarks=request.form.get("remarks", ""),
                    )
                except ValueError as exc:
                    error = str(exc)
                    data = get_direct_image_verification(
                        db, user=current_user, project_id=project_id, uuid=str(uuid)
                    )
            else:
                data = get_direct_image_verification(
                    db, user=current_user, project_id=project_id, uuid=str(uuid)
                )
            response = make_response(render_template(
                "projects/_direct_verification_panel.html", data=data, error=error
            ))
            if request.method == "POST" and error is None:
                response.headers["HX-Trigger"] = "direct-image-verified"
            return response
    except ProjectReviewNotFound as exc:
        return jsonify({"success": False, "error": str(exc)}), 404


@api_bp.route("/projects/<int:project_id>/review/gradings", methods=["GET"])
@login_required
def project_review_gradings(project_id: int):
    try:
        with transaction_scope() as db:
            return _response(get_gradings(db, user=current_user, project_id=project_id))
    except ProjectReviewNotFound as exc:
        return jsonify({"success": False, "error": str(exc)}), 404


@api_bp.route("/projects/<int:project_id>/exports/preview", methods=["GET"])
@login_required
def project_export_preview_api(project_id: int):
    try:
        export_request = _project_export_request(project_id, current_user.id, kind="workbook")
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    with transaction_scope() as db:
        allowed_labs = authorized_project_export_labs(
            db, actor=current_user, project_id=project_id
        )
        if not allowed_labs:
            return jsonify({"success": False, "error": "Project not found."}), 404
        return jsonify({
            "success": True,
            "data": project_export_preview(db, export_request, allowed_labs),
        })


@api_bp.route("/projects/<int:project_id>/exports", methods=["POST"])
@login_required
def create_project_export(project_id: int):
    try:
        export_request = _project_export_request(project_id, current_user.id)
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    with transaction_scope() as db:
        allowed_labs = authorized_project_export_labs(
            db, actor=current_user, project_id=project_id
        )
        if not allowed_labs:
            return jsonify({"success": False, "error": "Project not found."}), 404
        preview = project_export_preview(db, export_request, allowed_labs)
        if export_request.kind == "images" and not preview["image_export_allowed"]:
            return jsonify({
                "success": False,
                "error": (
                    f"Image exports are limited to 250 EncounterSets; "
                    f"the current filters match {preview['encounter_count']}."
                ),
            }), 400
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    job_token = db_create_job(
        ["project_export"], [],
        uploader_user_id=current_user.id,
        uploader_username=current_user.username,
        uploader_ip=xff or request.remote_addr or "-",
        project_id=project_id,
        upload_type="project_export",
    )
    request_data = {
        "project_id": export_request.project_id,
        "actor_user_id": export_request.actor_user_id,
        "kind": export_request.kind,
        "date_from": export_request.date_from.isoformat() if export_request.date_from else None,
        "date_to": export_request.date_to.isoformat() if export_request.date_to else None,
        "grading_filter": export_request.grading_filter,
    }
    enqueue_project_export(current_app._get_current_object(), job_token, request_data)
    return jsonify({
        "success": True,
        "data": {
            "job_token": job_token,
            "status_url": url_for("jobs.job_status_page", job_token=job_token),
        },
    }), 202


@api_bp.route("/projects/<int:project_id>/exports/recent", methods=["GET"])
@login_required
def recent_project_exports(project_id: int):
    with transaction_scope() as db:
        allowed_labs = authorized_project_export_labs(
            db, actor=current_user, project_id=project_id
        )
        if not allowed_labs:
            return jsonify({"success": False, "error": "Project not found."}), 404
        history = project_export_history(
            db, project_id=project_id, actor_user_id=current_user.id
        )
    return jsonify({
        "success": True,
        "data": [{
            "job_token": item.token,
            "status": item.status,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "status_url": url_for("jobs.job_status_page", job_token=item.token),
            "files": [{
                "filename": filename,
                "download_url": url_for(
                    "fundus_api.download_project_export",
                    project_id=project_id,
                    job_token=item.token,
                    filename=filename,
                ),
            } for filename in item.files],
        } for item in history],
    })


@api_bp.route("/projects/<int:project_id>/exports/<job_token>/<filename>", methods=["GET"])
@login_required
def download_project_export(project_id: int, job_token: str, filename: str):
    if secure_filename(filename) != filename:
        return jsonify({"success": False, "error": "File not found."}), 404
    with transaction_scope() as db:
        allowed_labs = authorized_project_export_labs(
            db, actor=current_user, project_id=project_id
        )
        job = db.execute(select(Job).where(
            Job.token == job_token,
            Job.project_id == project_id,
            Job.upload_type == "project_export",
            Job.uploader_user_id == current_user.id,
        )).scalar_one_or_none()
        if not allowed_labs or job is None:
            return jsonify({"success": False, "error": "File not found."}), 404
    export_dir = (EXPORT_DIR / job_token).resolve()
    if EXPORT_DIR.resolve() not in export_dir.parents:
        return jsonify({"success": False, "error": "File not found."}), 404
    return send_from_directory(export_dir, filename, as_attachment=True)
