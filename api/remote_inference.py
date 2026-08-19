"""JSON APIs for project-owned manual remote inference workflows."""
from __future__ import annotations

from flask import flash, jsonify, render_template, request, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import Project
from remote_inference import automated_service, encounter_service, job_service, manual_service
from remote_inference.dr_dme import ALLOWED_PAGE_SIZES, CandidateFilters, list_candidates as list_dr_dme_candidates
from upload_profiles.service import get_user_lab_unit_ids, manager_lab_unit_ids

from . import api_bp


def _json_result(result):
    flash(result.message, "success" if result.success else "danger")
    payload = dict(result.payload or {})
    if result.success:
        return jsonify(
            success=True,
            message=result.message,
            redirect_url=url_for("admin.upload_projects_admin"),
            **payload,
        ), result.status_code
    return jsonify(success=False, message=result.message, error=result.message, **payload), result.status_code


@api_bp.route("/remote-inference/projects/<int:project_id>/manual-workflows", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def get_project_manual_remote_inference_workflows(project_id: int):
    """Return the project's available and enabled manual remote workflows."""
    if not manager_lab_unit_ids(current_user.id):
        return jsonify(success=False, error="You are not assigned to any lab units for remote inference management."), 403
    with get_db_session() as db:
        if db.get(Project, project_id) is None:
            return jsonify(success=False, error="Project not found."), 404
        context = manual_service.project_manual_workflow_context(db, project_id)
        rows = [
            {
                "disease_id": row.disease_id,
                "disease_name": row.disease_name,
                "ai_model_id": row.ai_model_id,
                "ai_model_name": row.ai_model_name,
                "ai_model_version": row.ai_model_version,
                "provider": row.provider,
                "upload_kind": row.upload_kind,
                "enabled": row.enabled,
            }
            for row in context["manual_remote_inference_workflows"]
        ]
    return jsonify(success=True, project_id=project_id, manual_workflows=rows)


@api_bp.route("/remote-inference/projects/<int:project_id>/manual-workflows", methods=["POST", "PATCH"])
@roles_required("admin", "local_admin", "data_manager")
def save_project_manual_remote_inference_workflows(project_id: int):
    """Replace the project's enabled manual remote inference workflows."""
    if request.is_json:
        body = request.get_json(silent=True) or {}
        values = body.get("manual_remote_inference_workflows") or []
    else:
        values = request.form.getlist("manual_remote_inference_workflow")
    workflows = manual_service.workflow_keys_from_values(values)
    return _json_result(manual_service.set_project_manual_workflows(current_user.id, project_id, workflows))


@api_bp.route("/remote-inference/projects/<int:project_id>/automated-workflows", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def get_project_automated_remote_inference_workflows(project_id: int):
    """Return profile-derived options and project-owned automated rules."""
    if not manager_lab_unit_ids(current_user.id):
        return jsonify(success=False, error="You are not assigned to any lab units for remote inference management."), 403
    with get_db_session() as db:
        if db.get(Project, project_id) is None:
            return jsonify(success=False, error="Project not found."), 404
        context = automated_service.project_automated_workflow_context(db, project_id)
        rows = [
            {
                "disease_id": row.disease_id, "disease_name": row.disease_name,
                "ai_model_id": row.ai_model_id, "ai_model_name": row.ai_model_name,
                "ai_model_version": row.ai_model_version, "provider": row.provider,
                "upload_kind": row.upload_kind, "supporting_profiles": list(row.supporting_profiles),
                "enabled": row.enabled, "trigger_timing": row.trigger_timing,
                "encounter_eligibility": row.encounter_eligibility,
                "image_selection": row.image_selection,
            }
            for row in context["automated_remote_inference_workflows"]
        ]
    return jsonify(success=True, project_id=project_id, automated_workflows=rows)


@api_bp.route("/remote-inference/projects/<int:project_id>/wadhwani/encounter-set-jobs", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def get_recent_project_wadhwani_encounter_set_jobs(project_id: int):
    """Return the latest 10 scoped EncounterSet Wadhwani jobs for a project."""
    allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    with get_db_session() as db:
        if db.get(Project, project_id) is None:
            return jsonify(success=False, error="Project not found."), 404
        jobs = job_service.list_recent_encounter_set_wadhwani_jobs(
            db,
            project_id=project_id,
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            limit=10,
        )
    if request.headers.get("HX-Request") == "true":
        return render_template(
            "remidio_api_uploads/_recent_wadhwani_jobs.html",
            jobs=jobs,
            project_id=project_id,
        )
    return jsonify(
        success=True,
        project_id=project_id,
        jobs=[
            {
                "token": row.token,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "total_count": row.total_count,
                "queued_count": row.queued_count,
                "processing_count": row.processing_count,
                "completed_count": row.completed_count,
                "failed_count": row.failed_count,
                "status_url": url_for(
                    "remidio_api_uploads.encounter_set_wadhwani_inference_job",
                    job_token=row.token,
                ),
            }
            for row in jobs
        ],
    )


@api_bp.route("/remote-inference/projects/<int:project_id>/automated-workflows", methods=["POST", "PATCH"])
@roles_required("admin", "local_admin", "data_manager")
def save_project_automated_remote_inference_workflows(project_id: int):
    """Replace the project's active automated rules with capability validation."""
    if request.is_json:
        body = request.get_json(silent=True) or {}
        values = body.get("automated_remote_inference_workflows") or []
    else:
        values = []
        for token in request.form.getlist("automated_remote_inference_workflow"):
            parts = str(token).split(":")
            if len(parts) != 3:
                continue
            prefix = f"automated_remote_rule_{parts[0]}_{parts[1]}_{parts[2]}"
            values.append({
                "disease_id": parts[0], "ai_model_id": parts[1], "upload_kind": parts[2],
                "trigger_timing": "on_image_received",
                "encounter_eligibility": request.form.get(f"{prefix}_encounter_eligibility") or "always",
                "image_selection": request.form.get(f"{prefix}_image_selection") or "all_eligible_images",
            })
    rules = automated_service.rule_inputs_from_values(values)
    return _json_result(automated_service.set_project_automated_rules(current_user.id, project_id, rules))


@api_bp.route("/remote-inference/wadhwani/encounter-set-jobs/<job_token>/resume", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def resume_interrupted_wadhwani_encounter_set_job(job_token: str):
    """Resume only the unfinished portion of a stale manual Wadhwani batch."""
    return _json_result(
        job_service.resume_interrupted_wadhwani_job(job_token=job_token, user_id=current_user.id)
    )


@api_bp.route("/remote-inference/projects/<int:project_id>/encounter-workflows/dr-dme", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def get_project_dr_dme_encounter_workflow(project_id: int):
    """Return capability and independent automatic/manual DR-DME controls."""
    if not manager_lab_unit_ids(current_user.id):
        return jsonify(success=False, error="You are not assigned to any lab units for remote inference management."), 403
    with get_db_session() as db:
        if db.get(Project, project_id) is None:
            return jsonify(success=False, error="Project not found."), 404
        payload = encounter_service.workflow_context(db, project_id)
    return jsonify(success=True, project_id=project_id, workflow=payload)


@api_bp.route("/remote-inference/projects/<int:project_id>/encounter-workflows/dr-dme", methods=["POST", "PATCH"])
@roles_required("admin", "local_admin", "data_manager")
def save_project_dr_dme_encounter_workflow(project_id: int):
    """Save independent automatic/manual controls for the encounter workflow."""
    body = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    body = body or {}
    if not request.is_json:
        body["automatic_enabled"] = request.form.get("automatic_enabled") in {"1", "true", "on"}
        body["manual_enabled"] = request.form.get("manual_enabled") in {"1", "true", "on"}
    return _json_result(encounter_service.save_workflow(current_user.id, project_id, body))


@api_bp.route("/remote-inference/encounter-set-candidates", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "fileUploader")
def get_encounter_remote_inference_candidates():
    """List authorized, verified EncounterSets with DR-DME eligibility details."""
    try:
        project_id = int(request.args.get("project_id", ""))
    except (TypeError, ValueError):
        return jsonify(success=False, error="project_id is required."), 400
    workflow = request.args.get("workflow") or "dr_dme"
    if workflow != "dr_dme":
        return jsonify(success=False, error="Unsupported encounter workflow."), 400

    def optional_int(name: str, default: int) -> int:
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    filters = CandidateFilters(
        project_id=project_id,
        capture_date_from=str(request.args.get("capture_date_from") or ""),
        capture_date_to=str(request.args.get("capture_date_to") or ""),
        camera_id=str(request.args.get("camera_id") or ""),
        dr_report=str(request.args.get("dr_report") or ""),
        include_prior=request.args.get("include_prior") in {"1", "true", "on", "yes"},
        page=optional_int("page", 1),
        page_size=optional_int("page_size", ALLOWED_PAGE_SIZES[0]),
    ).normalized()
    with get_db_session() as db:
        if db.get(Project, project_id) is None:
            return jsonify(success=False, error="Project not found."), 404
        result = list_dr_dme_candidates(db, filters=filters, user=current_user)
    rows = []
    for row in result.rows:
        serialized = dict(row)
        capture_date = serialized.get("capture_date")
        serialized["capture_date"] = capture_date.isoformat() if hasattr(capture_date, "isoformat") else capture_date
        rows.append(serialized)
    return jsonify(
        success=True,
        project_id=project_id,
        workflow_key=workflow,
        candidates=rows,
        filters={
            "capture_date_from": filters.capture_date_from,
            "capture_date_to": filters.capture_date_to,
            "camera_id": filters.camera_id,
            "dr_report": filters.dr_report,
            "include_prior": filters.include_prior,
        },
        pagination={
            "page": result.page,
            "page_size": result.page_size,
            "encounter_count": result.encounter_count,
            "image_count": result.image_count,
            "has_prev": result.has_prev,
            "has_next": result.has_next,
        },
    )


@api_bp.route("/remote-inference/encounter-set-jobs", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager", "fileUploader")
def create_encounter_remote_inference_job():
    """Queue up to 100 authorized EncounterSets, with one job item per encounter."""
    body = request.get_json(silent=True) if request.is_json else request.form
    body = body or {}
    if str(body.get("workflow") or "dr_dme") != "dr_dme":
        return jsonify(success=False, error="Unsupported encounter workflow."), 400
    try:
        project_id = int(body.get("project_id"))
        encounter_ids = body.get("encounter_ids") if request.is_json else request.form.getlist("encounter_ids")
        encounter_ids = [int(value) for value in (encounter_ids or [])]
    except (TypeError, ValueError):
        return jsonify(success=False, error="project_id and integer encounter_ids are required."), 400
    result = encounter_service.create_manual_job(
        encounter_ids=encounter_ids,
        project_id=project_id,
        user=current_user,
        remote_addr=request.remote_addr,
    )
    payload = dict(result.payload or {})
    return jsonify(success=result.success, message=result.message, **payload), result.status_code
