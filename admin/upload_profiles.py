"""Admin routes for projects and upload profiles."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import (
    Area,
    AIModel,
    AIModelDisease,
    Camera,
    Disease,
    EncounterSetType,
    LabUnit,
    Project,
    ProjectInvestigator,
    User,
    user_lab_units,
)
from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding, RemidioApiSourceRule
from upload_profiles.service import manager_lab_unit_ids
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileArea,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeGradingPackage,
    UploadProfileEncounterSetTypeImageGradingScheme,
    UploadProfileEncounterSetTypePackageEncounterScheme,
    UploadProfileEncounterSetTypePackageImageScheme,
)


def _manager_lab_unit_ids() -> set[int]:
    """Return lab units the current manager can administer without overrides."""
    return manager_lab_unit_ids(current_user.id)


def _mapping_form_context(db, scoped_lab_ids: set[int]) -> dict:
    """Build detached-safe context for upload profile management templates."""
    lab_units = (
        db.execute(
            select(LabUnit)
            .options(selectinload(LabUnit.hospital))
            .where(LabUnit.id.in_(scoped_lab_ids))
            .order_by(LabUnit.name)
        )
        .scalars()
        .all()
    )
    users = (
        db.execute(
            select(User)
            .join(user_lab_units, user_lab_units.c.user_id == User.id)
            .where(user_lab_units.c.lab_unit_id.in_(scoped_lab_ids), User.is_active.is_(True))
            .options(selectinload(User.lab_units), selectinload(User.roles))
            .distinct()
            .order_by(User.username)
        )
        .scalars()
        .all()
    )
    projects = db.execute(select(Project).order_by(Project.active.desc(), Project.title)).scalars().all()
    upload_profiles = (
        db.execute(
            select(UploadProfile)
            .options(
                selectinload(UploadProfile.project_mappings).selectinload(ProjectUploadProfile.project),
                selectinload(UploadProfile.project_mappings)
                .selectinload(ProjectUploadProfile.assignments)
                .selectinload(ProjectUploadProfileAssignment.user),
                selectinload(UploadProfile.project_mappings)
                .selectinload(ProjectUploadProfile.assignments)
                .selectinload(ProjectUploadProfileAssignment.lab_unit),
                selectinload(UploadProfile.diseases).selectinload(UploadProfileDisease.disease),
                selectinload(UploadProfile.cameras).selectinload(UploadProfileCamera.camera),
                selectinload(UploadProfile.areas).selectinload(UploadProfileArea.area),
                selectinload(UploadProfile.ai_workflows),
                selectinload(UploadProfile.encounter_set_types).selectinload(UploadProfileEncounterSetType.encounter_set_type),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.encounter_grading_scheme),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.default_image_grading_scheme),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypeImageGradingScheme.disease),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageImageScheme.disease),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.encounter_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageEncounterScheme.disease),
            )
            .order_by(UploadProfile.active.desc(), UploadProfile.name)
        )
        .scalars()
        .unique()
        .all()
    )
    project_profile_mappings = (
        db.execute(
            select(ProjectUploadProfile)
            .options(
                selectinload(ProjectUploadProfile.project),
                selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.diseases).selectinload(UploadProfileDisease.disease),
                selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.cameras).selectinload(UploadProfileCamera.camera),
                selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.areas).selectinload(UploadProfileArea.area),
                selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.upload_kinds),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.encounter_set_type),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.encounter_grading_scheme),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.default_image_grading_scheme),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypeImageGradingScheme.disease),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageImageScheme.disease),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.encounter_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageEncounterScheme.disease),
                selectinload(ProjectUploadProfile.assignments).selectinload(ProjectUploadProfileAssignment.user),
                selectinload(ProjectUploadProfile.assignments).selectinload(ProjectUploadProfileAssignment.lab_unit),
                selectinload(ProjectUploadProfile.remidio_api_bindings)
                .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule)
                .selectinload(RemidioApiSourceRule.connection),
                selectinload(ProjectUploadProfile.remidio_api_bindings)
                .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule)
                .selectinload(RemidioApiSourceRule.site),
                selectinload(ProjectUploadProfile.remidio_api_bindings).selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit),
                selectinload(ProjectUploadProfile.remidio_api_bindings).selectinload(ProjectUploadProfileRemidioApiBinding.camera),
            )
            .order_by(ProjectUploadProfile.project_id, ProjectUploadProfile.active.desc(), ProjectUploadProfile.upload_profile_id)
        )
        .scalars()
        .unique()
        .all()
    )
    investigators = (
        db.execute(
            select(ProjectInvestigator)
            .options(selectinload(ProjectInvestigator.project), selectinload(ProjectInvestigator.user))
            .order_by(ProjectInvestigator.project_id, ProjectInvestigator.user_id)
        )
        .scalars()
        .all()
    )
    ai_models = (
        db.execute(
            select(AIModel)
            .join(AIModelDisease, AIModelDisease.ai_model_id == AIModel.id)
            .where(AIModelDisease.active.is_(True))
            .options(
                selectinload(AIModel.integration),
                selectinload(AIModel.disease_links).selectinload(AIModelDisease.disease),
            )
            .order_by(AIModel.name, AIModel.version)
        )
        .scalars()
        .unique()
        .all()
    )
    ai_models_by_disease: dict[int, list[AIModel]] = {}
    for model in ai_models:
        for link in model.disease_links:
            if link.active:
                ai_models_by_disease.setdefault(link.disease_id, []).append(model)
    project_cards = []
    for project in projects:
        active_investigators = [investigator for investigator in investigators if investigator.project_id == project.id and investigator.active]
        project_mappings = [mapping for mapping in project_profile_mappings if mapping.project_id == project.id]
        pi_names = [
            investigator.user.full_name or investigator.user.username
            for investigator in active_investigators
            if investigator.role == "principal_investigator"
        ]
        project_cards.append(
            {
                "project": project,
                "pi_names": pi_names,
                "investigator_count": len(active_investigators),
                "mapping_count": sum(1 for mapping in project_mappings if mapping.active and mapping.profile and mapping.profile.active),
                "uploader_count": len(
                    {
                        assignment.user_id
                        for mapping in project_mappings
                        for assignment in mapping.assignments
                        if (
                            mapping.active
                            and mapping.profile
                            and mapping.profile.active
                            and not mapping.profile.automated_remidio_populated
                            and assignment.active
                            and assignment.lab_unit_id in scoped_lab_ids
                        )
                    }
                ),
            }
        )

    return {
        "lab_units": lab_units,
        "scoped_lab_ids": scoped_lab_ids,
        "users": users,
        "projects": projects,
        "project_cards": project_cards,
        "diseases": db.execute(select(Disease).order_by(Disease.name)).scalars().all(),
        "cameras": db.execute(select(Camera).order_by(Camera.name)).scalars().all(),
        "areas": db.execute(select(Area).order_by(Area.name)).scalars().all(),
        "encounter_set_types": (
            db.execute(
                select(EncounterSetType)
                .order_by(EncounterSetType.active.desc(), EncounterSetType.name)
            )
            .scalars()
            .all()
        ),
        "ai_models_by_disease": ai_models_by_disease,
        "upload_profiles": upload_profiles,
        "project_profile_mappings": project_profile_mappings,
        "investigators": investigators,
        "remidio_api_source_rules": (
            db.execute(
                select(RemidioApiSourceRule)
                .options(selectinload(RemidioApiSourceRule.connection), selectinload(RemidioApiSourceRule.site))
                .order_by(RemidioApiSourceRule.active.desc(), RemidioApiSourceRule.site_custom_identifier, RemidioApiSourceRule.remidio_device_type)
            )
            .scalars()
            .all()
        ),
    }


@roles_required("admin", "local_admin", "data_manager")
def upload_profiles_admin():
    """Render dedicated upload profile CRUD."""
    scoped_lab_ids = _manager_lab_unit_ids()
    if not scoped_lab_ids:
        flash("You are not assigned to any lab units for upload profile management.", "warning")
        return redirect(url_for("admin.users_list"))

    with transaction_scope() as db:
        context = _mapping_form_context(db, scoped_lab_ids)
        context["profiles_only"] = True
        return render_template("admin/upload_profiles.html", **context)


@roles_required("admin", "local_admin", "data_manager")
def upload_projects_admin():
    """Render project and investigator governance."""
    scoped_lab_ids = _manager_lab_unit_ids()
    if not scoped_lab_ids:
        flash("You are not assigned to any lab units for project management.", "warning")
        return redirect(url_for("admin.users_list"))

    with transaction_scope() as db:
        context = _mapping_form_context(db, scoped_lab_ids)
        context["projects_only"] = True
        return render_template("admin/upload_projects.html", **context)


@roles_required("admin", "local_admin", "data_manager")
def upload_project_workspace(project_id: int):
    """Render one project management workspace fragment."""
    scoped_lab_ids = _manager_lab_unit_ids()
    if not scoped_lab_ids:
        return render_template("admin/partials/project_detail_panel.html", selected_project=None), 403

    with transaction_scope() as db:
        context = _mapping_form_context(db, scoped_lab_ids)
        selected_project = next((project for project in context["projects"] if project.id == project_id), None)
        if not selected_project:
            return render_template("admin/partials/project_detail_panel.html", selected_project=None), 404
        context["selected_project"] = selected_project
        context["project_investigators"] = [
            investigator for investigator in context["investigators"] if investigator.project_id == project_id and investigator.active
        ]
        context["project_profile_mappings"] = [
            mapping for mapping in context["project_profile_mappings"] if mapping.project_id == project_id
        ]
        context["enabled_profile_ids"] = {
            mapping.upload_profile_id for mapping in context["project_profile_mappings"] if mapping.active
        }
        context["selected_profile_id"] = request.args.get("profile_id", type=int)
        return render_template("admin/partials/project_detail_panel.html", **context)


@roles_required("admin", "local_admin", "data_manager")
def upload_project_create_workspace():
    """Render project create workspace fragment."""
    scoped_lab_ids = _manager_lab_unit_ids()
    if not scoped_lab_ids:
        return render_template("admin/partials/project_create_panel.html"), 403
    return render_template("admin/partials/project_create_panel.html")
