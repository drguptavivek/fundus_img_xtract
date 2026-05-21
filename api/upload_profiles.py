"""JSON APIs for project and upload-profile administration."""
from __future__ import annotations

from flask import flash, jsonify, request, url_for
from flask_login import current_user

from auth.roles import roles_required
from upload_profiles import admin_service as upload_profile_service

from . import api_bp


def _project_input_from_request() -> upload_profile_service.ProjectCreateInput:
    form = request.form
    return upload_profile_service.ProjectCreateInput(
        title=(form.get("title") or "").strip(),
        code=(form.get("code") or "").strip().upper(),
        description=(form.get("description") or "").strip() or None,
    )


def _investigator_input_from_request() -> upload_profile_service.InvestigatorCreateInput:
    form = request.form
    return upload_profile_service.InvestigatorCreateInput(
        project_id=upload_profile_service.to_int(form.get("project_id")),
        user_id=upload_profile_service.to_int(form.get("user_id")),
        role=form.get("role") or "co_investigator",
    )


def _assignment_input_from_request() -> upload_profile_service.ProfileAssignmentInput:
    form = request.form
    return upload_profile_service.ProfileAssignmentInput(
        profile_id=upload_profile_service.to_int(form.get("profile_id")),
        user_id=upload_profile_service.to_int(form.get("user_id")),
    )


def _profile_input_from_request() -> upload_profile_service.UploadProfileInput:
    form = request.form
    user_ids = None
    if "user_ids" in form or "user_id" in form:
        user_ids = upload_profile_service.to_int_list(form.getlist("user_ids") or form.getlist("user_id"))
    disease_ids = upload_profile_service.to_int_list(form.getlist("disease_ids") or form.getlist("disease_id"))
    default_disease_ids = upload_profile_service.to_int_list(form.getlist("default_disease_ids") or form.getlist("default_disease_id"))
    encounter_set_type_ids = upload_profile_service.to_int_list(
        form.getlist("encounter_set_type_ids") or form.getlist("encounter_set_type_id")
    )
    ai_workflows = []
    for value in form.getlist("ai_workflows"):
        parts = value.split(":")
        if len(parts) != 3:
            continue
        disease_id = upload_profile_service.to_int(parts[0])
        ai_model_id = upload_profile_service.to_int(parts[1])
        upload_kind = parts[2]
        if disease_id and ai_model_id and upload_kind:
            ai_workflows.append(
                upload_profile_service.AIWorkflowInput(
                    disease_id=disease_id,
                    ai_model_id=ai_model_id,
                    upload_kind=upload_kind,
                )
            )
    return upload_profile_service.UploadProfileInput(
        name=(form.get("name") or "").strip(),
        user_ids=user_ids,
        lab_unit_id=upload_profile_service.to_int(form.get("lab_unit_id")),
        project_id=upload_profile_service.to_int(form.get("project_id")),
        disease_ids=disease_ids,
        default_disease_ids=default_disease_ids,
        camera_ids=upload_profile_service.to_int_list(form.getlist("camera_ids")),
        area_ids=upload_profile_service.to_int_list(form.getlist("area_ids")),
        upload_kinds=form.getlist("upload_kinds") or ["direct_image"],
        allow_mydriatic=form.get("allow_mydriatic") == "on",
        allow_non_mydriatic=form.get("allow_non_mydriatic") == "on",
        default_is_mydriatic=form.get("default_is_mydriatic") == "on",
        ai_workflows=ai_workflows,
        encounter_set_type_ids=encounter_set_type_ids,
        description=(form.get("description") or "").strip() or None,
    )


def _json_result(result: upload_profile_service.MutationResult, *, redirect_endpoint: str = "admin.upload_profiles_admin"):
    flash(result.message, "success" if result.success else "danger")
    payload = {
        "success": result.success,
        "message": result.message,
        "redirect_url": url_for(redirect_endpoint),
    }
    if not result.success:
        payload["error"] = result.message
    if result.payload:
        payload.update(result.payload)
    return jsonify(payload), result.status_code


@api_bp.route("/upload-profiles/projects", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def create_upload_profile_project():
    """Create a project for upload profile governance."""
    dto = _project_input_from_request()
    return _json_result(upload_profile_service.create_project(dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/projects/<int:project_id>", methods=["PATCH", "POST"])
@roles_required("admin", "local_admin", "data_manager")
def update_upload_profile_project(project_id: int):
    """Update a project for upload profile governance."""
    dto = _project_input_from_request()
    return _json_result(upload_profile_service.update_project(project_id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/investigators", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def add_upload_profile_investigator():
    """Assign a project investigator."""
    dto = _investigator_input_from_request()
    return _json_result(upload_profile_service.add_investigator(dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/assignments", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def assign_upload_profile_user():
    """Assign a user to an upload profile through project governance."""
    dto = _assignment_input_from_request()
    return _json_result(upload_profile_service.assign_profile_user(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/assignments/remove", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def remove_upload_profile_user():
    """Remove a user assignment from an upload profile."""
    dto = _assignment_input_from_request()
    return _json_result(upload_profile_service.remove_profile_user(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def create_upload_profile():
    """Create an upload profile."""
    dto = _profile_input_from_request()
    return _json_result(upload_profile_service.create_profile(current_user.id, dto))


@api_bp.route("/upload-profiles/<int:profile_id>", methods=["PATCH", "POST"])
@roles_required("admin", "local_admin", "data_manager")
def update_upload_profile(profile_id: int):
    """Update an upload profile."""
    dto = _profile_input_from_request()
    return _json_result(upload_profile_service.update_profile(current_user.id, profile_id, dto))


@api_bp.route("/upload-profiles/<int:profile_id>/activate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def activate_upload_profile(profile_id: int):
    """Activate an upload profile."""
    return _json_result(upload_profile_service.set_profile_active(current_user.id, profile_id, True))


@api_bp.route("/upload-profiles/<int:profile_id>/deactivate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def deactivate_upload_profile(profile_id: int):
    """Deactivate an upload profile."""
    return _json_result(upload_profile_service.set_profile_active(current_user.id, profile_id, False))


@api_bp.route("/upload-profiles/<int:profile_id>/duplicate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def duplicate_upload_profile(profile_id: int):
    """Duplicate an upload profile without copying assignments."""
    return _json_result(upload_profile_service.duplicate_profile(current_user.id, profile_id))
