"""REST API for scoped non-PII project review data."""
from __future__ import annotations

from dataclasses import asdict

from flask import jsonify, request
from flask_login import current_user, login_required

from db_transaction_manager import transaction_scope
from project_review.exceptions import ProjectReviewNotFound
from project_review.service import get_gradings, get_summary, get_uploads, list_projects

from . import api_bp


def _response(data):
    return jsonify({"success": True, "data": asdict(data) if not isinstance(data, tuple) else [asdict(row) for row in data]})


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
            return _response(get_uploads(
                db,
                user=current_user,
                project_id=project_id,
                page=request.args.get("page", 1, type=int),
                per_page=request.args.get("per_page", 100, type=int),
            ))
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
