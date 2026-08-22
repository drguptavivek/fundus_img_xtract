from flask import current_app, jsonify, render_template, request, url_for
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db_transaction_manager import get_db_session, transaction_scope

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import global_uploader_or_project_assignment_required
from models import User, LabUnit, Job, JobItem
from services.uploads.direct import (
    DirectUploadJobError,
    build_web_direct_upload_context,
    create_web_direct_upload_from_form,
    enqueue_direct_upload_post_commit,
)
from upload_profiles.service import UploadProfileError


# -------------------
# Direct Uploads API
# -------------------

@api_bp.route('/users/<int:user_id>/lab-units', methods=['GET'])
@login_required
@global_uploader_or_project_assignment_required("direct_image")
def get_lab_units(user_id):
    """Get lab units for a user."""
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if current_user.id != user_id:
            return jsonify({"error": "Forbidden"}), 403

        context = build_web_direct_upload_context(db=db, user_id=current_user.id)
        lab_units = context["lab_units"]
        
        return jsonify([{"id": lu["id"], "name": lu["name"]} for lu in lab_units])


@api_bp.route('/lab-units/<int:lab_unit_id>/hospital', methods=['GET'])
@login_required
@global_uploader_or_project_assignment_required("direct_image")
def get_hospital(lab_unit_id):
    """Get hospital for a lab unit."""
    with get_db_session() as db:
        context = build_web_direct_upload_context(db=db, user_id=current_user.id)
        allowed_ids = {item["id"] for item in context["lab_units"]}
        lu = db.execute(
            select(LabUnit)
            .where(LabUnit.id == lab_unit_id, LabUnit.id.in_(allowed_ids or {-1}))
            .options(selectinload(LabUnit.hospital))
        ).scalar_one_or_none()
        
        if not lu:
            return jsonify({"error": "Lab unit not found or access denied"}), 404
        return jsonify({"id": lu.hospital.id, "name": lu.hospital.name})


@api_bp.route('/upload-jobs/<job_token>/status', methods=['GET'])
@login_required
@global_uploader_or_project_assignment_required("direct_image")
def get_upload_status(job_token):
    """Get status of a direct upload job."""
    with get_db_session() as db:
        job = _scoped_job(db, job_token)
        if job is None:
            return jsonify({"error": "Upload job not found."}), 404
        return jsonify(_job_payload(job))


@api_bp.route("/direct-uploads/form", methods=["GET"])
@global_uploader_or_project_assignment_required("direct_image")
def direct_upload_form():
    """HTMX/JSON form options for browser direct uploads."""
    with get_db_session() as db:
        context = build_web_direct_upload_context(db=db, user_id=current_user.id)
        context["selected_project_id"] = request.args.get("project_id", type=int)
    if _wants_json():
        return jsonify(_options_payload(context))
    return render_template("direct_uploads/_upload_form.html", **context)


@api_bp.route("/direct-uploads/workspace", methods=["GET"])
@global_uploader_or_project_assignment_required("direct_image")
def direct_upload_workspace():
    """HTMX/JSON workspace for recent direct upload jobs."""
    with get_db_session() as db:
        context = build_web_direct_upload_context(db=db, user_id=current_user.id)
    if _wants_json():
        return jsonify({"recent_uploads": context["recent_uploads"], "messages": []})
    return render_template("direct_uploads/_workspace.html", recent_uploads=context["recent_uploads"], messages=[], result=None)


@api_bp.route("/direct-uploads/uploads/web", methods=["POST"])
@global_uploader_or_project_assignment_required("direct_image")
def create_direct_upload_web():
    """Session-auth HTMX/JSON endpoint for browser direct uploads."""
    try:
        with transaction_scope() as db:
            result = create_web_direct_upload_from_form(
                db=db,
                user_id=current_user.id,
                username=current_user.username,
                remote_addr=request.remote_addr,
                form=request.form,
                files=request.files,
            )
            token = result.job.token
            upload_ids = result.upload_ids_for_post_commit
            hospital_id = result.hospital_id_for_post_commit
            inference_task_ids = result.inference_task_ids_for_post_commit
    except UploadProfileError as exc:
        return _upload_error(exc.message, status_code=400)
    except DirectUploadJobError as exc:
        return _upload_error(exc.message, status_code=exc.status_code)

    enqueue_direct_upload_post_commit(
        current_app,
        user_id=current_user.id,
        upload_ids=upload_ids,
        job_token=token,
        hospital_id=hospital_id,
        inference_task_ids=inference_task_ids,
        username=current_user.username,
        remote_addr=request.remote_addr,
        lab_unit_id=request.form.get("lab_unit_id", type=int),
        project_id=request.form.get("project_id", type=int),
        upload_profile_id=request.form.get("profile_id", type=int),
    )

    messages = [("success", f"Uploaded {result.uploaded_count}, duplicates {result.duplicate_count}, rejected {result.rejected_count}")]
    if result.rejected_count:
        messages.append(("warning", f"{result.rejected_count} image(s) could not be processed."))

    if request.headers.get("HX-Request"):
        with get_db_session() as db:
            context = build_web_direct_upload_context(db=db, user_id=current_user.id)
            job = _scoped_job(db, token)
            result_payload = _job_payload(job) if job else None
        return render_template("direct_uploads/_workspace.html", recent_uploads=context["recent_uploads"], messages=messages, result=result_payload)

    return jsonify({"upload_token": token, "messages": messages}), 201


@api_bp.route("/direct-uploads/uploads/<job_token>/status", methods=["GET"])
@global_uploader_or_project_assignment_required("direct_image")
def direct_upload_status(job_token: str):
    with get_db_session() as db:
        job = _scoped_job(db, job_token)
        if job is None:
            return jsonify({"error": "Upload job not found."}), 404
        payload = _job_payload(job)
    if request.headers.get("HX-Request"):
        return render_template("direct_uploads/_job_status.html", job=payload)
    return jsonify(payload)


def _upload_error(message: str, *, status_code: int):
    if request.headers.get("HX-Request"):
        with get_db_session() as db:
            context = build_web_direct_upload_context(db=db, user_id=current_user.id)
        return render_template(
            "direct_uploads/_workspace.html",
            recent_uploads=context["recent_uploads"],
            messages=[("danger", message)],
            result=None,
        ), status_code
    return jsonify({"error": message}), status_code


def _scoped_job(db, job_token: str) -> Job | None:
    job = db.query(Job).filter_by(token=job_token).first()
    if not job:
        return None
    if job.uploader_user_id != current_user.id:
        if not current_user.has_role("admin"):
            return None
    return job


def _job_payload(job: Job) -> dict:
    items = sorted(job.items, key=lambda item: item.id or 0)
    return {
        "job_id": job.id,
        "job_token": job.token,
        "job_status": job.status,
        "status_url": url_for("fundus_api.direct_upload_status", job_token=job.token),
        "items": [{"filename": item.filename, "state": item.state, "detail": item.detail} for item in items],
    }


def _options_payload(context: dict) -> dict:
    return {
        "projects": context["projects"],
        "upload_profiles": context["upload_profiles"],
        "hospitals": context["hospitals"],
        "lab_units": context["lab_units"],
        "cameras": context["cameras"],
        "diseases": context["diseases"],
        "areas": context["areas"],
        "limits": {
            "max_files_per_upload": context["max_files_per_upload"],
            "per_file_mb_limit": context["per_file_mb_limit"],
            "lifetime_quota": context["lifetime_quota"],
        },
    }


def _wants_json() -> bool:
    return request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json"
