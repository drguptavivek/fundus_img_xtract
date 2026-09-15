"""REST API for scoped non-PII project review data."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date

from flask import jsonify, make_response, render_template, request, url_for
from flask_login import current_user, login_required

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

from . import api_bp


def _response(data):
    return jsonify({"success": True, "data": asdict(data) if not isinstance(data, tuple) else [asdict(row) for row in data]})


def _date_arg(name: str) -> date | None:
    value = request.args.get(name, "").strip()
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


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
