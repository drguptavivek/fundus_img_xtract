"""JSON APIs for project-owned manual remote inference workflows."""
from __future__ import annotations

from flask import flash, jsonify, request, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import Project
from remote_inference import automated_service, job_service, manual_service
from upload_profiles.service import manager_lab_unit_ids

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
