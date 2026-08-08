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


def _project_profile_input_from_request(project_id: int) -> upload_profile_service.ProjectProfileInput:
    form = request.form
    return upload_profile_service.ProjectProfileInput(
        project_id=project_id,
        upload_profile_id=upload_profile_service.to_int(form.get("upload_profile_id") or form.get("profile_id")),
    )


def _project_profile_assignment_input_from_request() -> upload_profile_service.ProjectProfileAssignmentInput:
    form = request.form
    return upload_profile_service.ProjectProfileAssignmentInput(
        project_upload_profile_id=upload_profile_service.to_int(form.get("project_upload_profile_id")),
        user_id=upload_profile_service.to_int(form.get("user_id")),
        lab_unit_ids=upload_profile_service.to_int_list(form.getlist("lab_unit_ids") or form.getlist("lab_unit_id")),
    )


def _project_profile_assignment_remove_input_from_request() -> upload_profile_service.ProjectProfileAssignmentRemoveInput:
    form = request.form
    return upload_profile_service.ProjectProfileAssignmentRemoveInput(
        assignment_id=upload_profile_service.to_int(form.get("assignment_id")),
    )


def _profile_input_from_request() -> upload_profile_service.UploadProfileInput:
    form = request.form
    disease_ids = upload_profile_service.to_int_list(form.getlist("disease_ids") or form.getlist("disease_id"))
    default_disease_ids = upload_profile_service.to_int_list(form.getlist("default_disease_ids") or form.getlist("default_disease_id"))
    encounter_set_type_ids = upload_profile_service.to_int_list(
        form.getlist("encounter_set_type_ids") or form.getlist("encounter_set_type_id")
    )
    encounter_set_configs = []
    for encounter_set_type_id in encounter_set_type_ids:
        packages = _encounter_set_packages_from_request(form, encounter_set_type_id)
        image_scheme_ids = upload_profile_service.to_int_list(
            form.getlist(f"encounter_set_type_{encounter_set_type_id}_image_grading_scheme_ids")
        )
        default_image_scheme_id = upload_profile_service.to_int(
            form.get(f"encounter_set_type_{encounter_set_type_id}_default_image_grading_scheme_id")
        )
        encounter_scheme_id = upload_profile_service.to_int(
            form.get(f"encounter_set_type_{encounter_set_type_id}_encounter_grading_scheme_id")
        )
        if packages:
            image_scheme_ids = sorted({disease_id for package in packages for disease_id in package.image_grading_scheme_ids})
            default_image_scheme_id = next((package.default_image_grading_scheme_id for package in packages if package.default_image_grading_scheme_id), None)
            encounter_scheme_id = next(
                (package.encounter_grading_scheme_ids[0] for package in packages if package.encounter_grading_scheme_ids),
                None,
            )
        encounter_set_configs.append(
            upload_profile_service.EncounterSetProfileInput(
                encounter_set_type_id=encounter_set_type_id,
                image_grading_scheme_ids=image_scheme_ids,
                default_image_grading_scheme_id=default_image_scheme_id,
                encounter_grading_scheme_id=encounter_scheme_id,
                grading_packages=packages,
            )
        )
    return upload_profile_service.UploadProfileInput(
        name=(form.get("name") or "").strip(),
        disease_ids=disease_ids,
        default_disease_ids=default_disease_ids,
        camera_ids=upload_profile_service.to_int_list(form.getlist("camera_ids")),
        area_ids=upload_profile_service.to_int_list(form.getlist("area_ids")),
        upload_kinds=form.getlist("upload_kinds"),
        allow_mydriatic=form.get("allow_mydriatic") == "on",
        allow_non_mydriatic=form.get("allow_non_mydriatic") == "on",
        default_is_mydriatic=form.get("default_is_mydriatic") == "on",
        automated_remidio_populated=form.get("automated_remidio_populated") == "on",
        allow_remidio_zip_encounter_set=form.get("allow_remidio_zip_encounter_set") == "on",
        allow_iitk_zip_encounter_set=form.get("allow_iitk_zip_encounter_set") == "on",
        encounter_set_configs=encounter_set_configs,
        task_prioritization_json=form.get("task_prioritization_json") or None,
        description=(form.get("description") or "").strip() or None,
    )


def _encounter_set_packages_from_request(form, encounter_set_type_id: int):
    raw_json = (form.get(f"encounter_set_type_{encounter_set_type_id}_grading_packages_json") or "").strip()
    packages = []
    if raw_json:
        import json
        try:
            rows = json.loads(raw_json)
        except json.JSONDecodeError:
            rows = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                packages.append(
                    upload_profile_service.EncounterSetGradingPackageInput(
                        name=str(row.get("name") or ""),
                        code=str(row.get("code") or ""),
                        applicability=str(row.get("applicability") or "always"),
                        grading_mode=str(row.get("grading_mode") or "unified"),
                        image_grading_scheme_ids=[
                            value for value in (
                                upload_profile_service.to_int(str(item)) for item in row.get("image_grading_scheme_ids", [])
                            )
                            if value is not None
                        ],
                        encounter_grading_scheme_ids=[
                            value for value in (
                                upload_profile_service.to_int(str(item)) for item in row.get("encounter_grading_scheme_ids", [])
                            )
                            if value is not None
                        ],
                        default_image_grading_scheme_id=upload_profile_service.to_int(
                            str(row.get("default_image_grading_scheme_id") or "")
                        ),
                        image_scheme_auto_create_policies={
                            int(key): str(value or "always")
                            for key, value in (row.get("image_scheme_auto_create_policies") or {}).items()
                            if str(key).isdigit()
                        },
                        image_scheme_negative_controls_per_positive={
                            int(key): upload_profile_service.to_int(str(value)) or 0
                            for key, value in (row.get("image_scheme_negative_controls_per_positive") or {}).items()
                            if str(key).isdigit()
                        },
                        image_scheme_metadata_rules={
                            int(key): upload_profile_service.ImageMetadataTaskRuleInput(
                                field_key=str(value.get("field_key") or ""),
                                match_value=str(value.get("match_value") or ""),
                            )
                            for key, value in (row.get("image_scheme_metadata_rules") or {}).items()
                            if str(key).isdigit() and isinstance(value, dict)
                        },
                    )
                )
    return packages


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
    dto = _project_profile_assignment_input_from_request()
    return _json_result(upload_profile_service.assign_project_profile_user(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/assignments/remove", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def remove_upload_profile_user():
    """Remove a user assignment from an upload profile."""
    dto = _project_profile_assignment_remove_input_from_request()
    return _json_result(upload_profile_service.remove_project_profile_assignment(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/projects/<int:project_id>/profiles", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def enable_upload_profile_for_project(project_id: int):
    """Enable a reusable upload profile template for one project."""
    dto = _project_profile_input_from_request(project_id)
    return _json_result(upload_profile_service.enable_project_profile(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/project-profiles/<int:project_upload_profile_id>/activate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def activate_project_upload_profile(project_upload_profile_id: int):
    """Reactivate an upload profile mapping for a project."""
    return _json_result(
        upload_profile_service.set_project_profile_active(current_user.id, project_upload_profile_id, True),
        redirect_endpoint="admin.upload_projects_admin",
    )


@api_bp.route("/upload-profiles/project-profiles/<int:project_upload_profile_id>/deactivate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def deactivate_project_upload_profile(project_upload_profile_id: int):
    """Deactivate an upload profile mapping for a project."""
    return _json_result(
        upload_profile_service.set_project_profile_active(current_user.id, project_upload_profile_id, False),
        redirect_endpoint="admin.upload_projects_admin",
    )


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
