"""JSON APIs for project and upload-profile administration."""
from __future__ import annotations

from flask import flash, jsonify, request, url_for
from flask_login import current_user, login_required

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import Project
from encounter_sets.permissions import (
    EncounterSetPermissionError,
    ProjectEncounterSetPermissionInput,
    list_project_permissions,
    set_project_permission,
)
from upload_profiles.service import explicit_lab_unit_ids
from upload_profiles import admin_service as upload_profile_service
from services.project_referral_diseases import (
    list_configured_project_referral_disease_ids,
    list_project_positive_disease_options,
    replace_project_referral_diseases,
)

from . import api_bp


def _request_bool(name: str, *, default: bool = False) -> bool:
    payload = request.get_json(silent=True) if request.is_json else None
    value = payload.get(name) if isinstance(payload, dict) else request.form.get(name)
    if value is None:
        return default
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _request_int(name: str) -> int:
    payload = request.get_json(silent=True) if request.is_json else None
    value = payload.get(name) if isinstance(payload, dict) else request.form.get(name)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise EncounterSetPermissionError(f"{name} must be an integer.") from exc


def _permission_json(row) -> dict:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "user_id": row.user_id,
        "username": row.user.username if row.user else None,
        "lab_unit_id": row.lab_unit_id,
        "lab_unit_name": row.lab_unit.name if row.lab_unit else None,
        "can_browse": row.can_browse,
        "can_verify": row.can_verify,
        "can_upload": row.can_upload,
        "can_review_discrepancies": row.can_review_discrepancies,
        "can_export_data": row.can_export_data,
        "can_view_analytics": row.can_view_analytics,
        "can_create_datasets": row.can_create_datasets,
        "can_adjudicate_regrades": row.can_adjudicate_regrades,
        "active": row.active,
    }


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
                        root_image_grading_scheme_id=upload_profile_service.to_int(
                            str(row.get("root_image_grading_scheme_id") or "")
                        ),
                        encounter_scheme_by_image_disease_id={
                            int(key): int(value)
                            for key, value in (
                                row.get("encounter_scheme_by_image_disease_id") or {}
                            ).items()
                            if str(key).isdigit() and str(value).isdigit()
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
@roles_required("admin")
def create_upload_profile_project():
    """Create a project for upload profile governance."""
    dto = _project_input_from_request()
    return _json_result(upload_profile_service.create_project(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/projects/<int:project_id>", methods=["PATCH", "POST"])
@roles_required("admin")
def update_upload_profile_project(project_id: int):
    """Update a project for upload profile governance."""
    dto = _project_input_from_request()
    return _json_result(upload_profile_service.update_project(current_user.id, project_id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/projects/<int:project_id>/referral-diseases", methods=["GET", "PUT", "POST"])
@roles_required("admin")
def project_referral_diseases(project_id: int):
    """Read or replace referral-only diseases allowed by one project."""
    with transaction_scope() as db:
        if db.get(Project, project_id) is None:
            return jsonify({"success": False, "error": "Project not found.", "message": "Project not found."}), 404
        if request.method != "GET":
            payload = request.get_json(silent=True) if request.is_json else None
            raw_ids = payload.get("disease_ids", []) if isinstance(payload, dict) else request.form.getlist("disease_ids")
            try:
                disease_ids = [int(value) for value in raw_ids]
                replace_project_referral_diseases(db, project_id=project_id, disease_ids=disease_ids)
            except (TypeError, ValueError) as exc:
                return jsonify({"success": False, "error": str(exc), "message": str(exc)}), 400

        configured_ids = list_configured_project_referral_disease_ids(db, project_id=project_id)
        options = list_project_positive_disease_options(db, project_id=project_id)
        payload = {
            "success": True,
            "message": "Project referral diseases updated." if request.method != "GET" else "Project referral diseases loaded.",
            "data": {
                "project_id": project_id,
                "configured_disease_ids": list(configured_ids),
                "effective_diseases": [
                    {"disease_id": option.disease_id, "name": option.name}
                    for option in options
                ],
            },
        }
        return jsonify(payload)


@api_bp.route("/projects/<int:project_id>/encounter-set-permissions", methods=["GET", "PUT", "POST"])
@roles_required("admin")
def project_encounter_set_permissions(project_id: int):
    """Read or upsert user/lab permissions for EncounterSet browsing and verification."""
    with transaction_scope() as db:
        if db.get(Project, project_id) is None:
            return jsonify({"success": False, "error": "Project not found."}), 404
        if request.method != "GET":
            try:
                row = set_project_permission(
                    db,
                    manager_user_id=current_user.id,
                    project_id=project_id,
                    data=ProjectEncounterSetPermissionInput(
                        user_id=_request_int("user_id"),
                        lab_unit_id=_request_int("lab_unit_id"),
                        can_browse=_request_bool("can_browse"),
                        can_verify=_request_bool("can_verify"),
                        can_upload=_request_bool("can_upload"),
                        can_review_discrepancies=_request_bool("can_review_discrepancies"),
                        can_export_data=_request_bool("can_export_data"),
                        can_view_analytics=_request_bool("can_view_analytics"),
                        can_create_datasets=_request_bool("can_create_datasets"),
                        can_adjudicate_regrades=_request_bool("can_adjudicate_regrades"),
                        active=_request_bool("active", default=True),
                    ),
                )
            except EncounterSetPermissionError as exc:
                return jsonify({"success": False, "error": str(exc), "message": str(exc)}), 400
            message = "EncounterSet permissions updated."
        else:
            row = None
            message = "EncounterSet permissions loaded."

        rows = list_project_permissions(
            db,
            project_id,
            lab_unit_ids=explicit_lab_unit_ids(db, current_user.id),
        )
        return jsonify({
            "success": True,
            "message": message,
            "data": {
                "project_id": project_id,
                "updated": _permission_json(row) if row else None,
                "permissions": [_permission_json(item) for item in rows],
            },
        })


@api_bp.route("/upload-profiles/investigators", methods=["POST"])
@roles_required("admin")
def add_upload_profile_investigator():
    """Assign a project investigator."""
    dto = _investigator_input_from_request()
    return _json_result(upload_profile_service.add_investigator(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/assignments", methods=["POST"])
@login_required
def assign_upload_profile_user():
    """Assign a user to an upload profile through project governance."""
    dto = _project_profile_assignment_input_from_request()
    return _json_result(upload_profile_service.assign_project_profile_user(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/assignments/remove", methods=["POST"])
@login_required
def remove_upload_profile_user():
    """Remove a user assignment from an upload profile."""
    dto = _project_profile_assignment_remove_input_from_request()
    return _json_result(upload_profile_service.remove_project_profile_assignment(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/projects/<int:project_id>/profiles", methods=["POST"])
@roles_required("admin")
def enable_upload_profile_for_project(project_id: int):
    """Enable a reusable upload profile template for one project."""
    dto = _project_profile_input_from_request(project_id)
    return _json_result(upload_profile_service.enable_project_profile(current_user.id, dto), redirect_endpoint="admin.upload_projects_admin")


@api_bp.route("/upload-profiles/project-profiles/<int:project_upload_profile_id>/activate", methods=["POST"])
@roles_required("admin")
def activate_project_upload_profile(project_upload_profile_id: int):
    """Reactivate an upload profile mapping for a project."""
    return _json_result(
        upload_profile_service.set_project_profile_active(current_user.id, project_upload_profile_id, True),
        redirect_endpoint="admin.upload_projects_admin",
    )


@api_bp.route("/upload-profiles/project-profiles/<int:project_upload_profile_id>/deactivate", methods=["POST"])
@roles_required("admin")
def deactivate_project_upload_profile(project_upload_profile_id: int):
    """Deactivate an upload profile mapping for a project."""
    return _json_result(
        upload_profile_service.set_project_profile_active(current_user.id, project_upload_profile_id, False),
        redirect_endpoint="admin.upload_projects_admin",
    )


@api_bp.route("/upload-profiles", methods=["POST"])
@roles_required("admin")
def create_upload_profile():
    """Create an upload profile."""
    dto = _profile_input_from_request()
    return _json_result(upload_profile_service.create_profile(current_user.id, dto))


@api_bp.route("/upload-profiles/<int:profile_id>", methods=["PATCH", "POST"])
@roles_required("admin")
def update_upload_profile(profile_id: int):
    """Update an upload profile."""
    dto = _profile_input_from_request()
    return _json_result(upload_profile_service.update_profile(current_user.id, profile_id, dto))


@api_bp.route("/upload-profiles/<int:profile_id>/activate", methods=["POST"])
@roles_required("admin")
def activate_upload_profile(profile_id: int):
    """Activate an upload profile."""
    return _json_result(upload_profile_service.set_profile_active(current_user.id, profile_id, True))


@api_bp.route("/upload-profiles/<int:profile_id>/deactivate", methods=["POST"])
@roles_required("admin")
def deactivate_upload_profile(profile_id: int):
    """Deactivate an upload profile."""
    return _json_result(upload_profile_service.set_profile_active(current_user.id, profile_id, False))


@api_bp.route("/upload-profiles/<int:profile_id>/duplicate", methods=["POST"])
@roles_required("admin")
def duplicate_upload_profile(profile_id: int):
    """Duplicate an upload profile without copying assignments."""
    return _json_result(upload_profile_service.duplicate_profile(current_user.id, profile_id))
