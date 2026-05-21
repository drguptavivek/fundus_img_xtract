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
from upload_profiles.service import manager_lab_unit_ids
from upload_profiles.models import (
    UploadProfile,
    UploadProfileArea,
    UploadProfileAssignment,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
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
            .where(UploadProfile.lab_unit_id.in_(scoped_lab_ids))
            .options(
                selectinload(UploadProfile.assignments).selectinload(UploadProfileAssignment.user),
                selectinload(UploadProfile.project),
                selectinload(UploadProfile.lab_unit),
                selectinload(UploadProfile.diseases).selectinload(UploadProfileDisease.disease),
                selectinload(UploadProfile.cameras).selectinload(UploadProfileCamera.camera),
                selectinload(UploadProfile.areas).selectinload(UploadProfileArea.area),
                selectinload(UploadProfile.ai_workflows),
                selectinload(UploadProfile.encounter_set_types).selectinload(UploadProfileEncounterSetType.encounter_set_type),
            )
            .order_by(UploadProfile.active.desc(), UploadProfile.project_id, UploadProfile.name)
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
                "mapping_count": sum(
                    1 for profile in upload_profiles if profile.project_id == project.id and profile.active
                ),
                "uploader_count": len(
                    {
                        assignment.user_id
                        for profile in upload_profiles
                        for assignment in profile.assignments
                        if profile.project_id == project.id and profile.active and assignment.active
                    }
                ),
            }
        )

    return {
        "lab_units": lab_units,
        "users": users,
        "projects": projects,
        "project_cards": project_cards,
        "diseases": db.execute(select(Disease).order_by(Disease.name)).scalars().all(),
        "cameras": db.execute(select(Camera).order_by(Camera.name)).scalars().all(),
        "areas": db.execute(select(Area).order_by(Area.name)).scalars().all(),
        "encounter_set_types": (
            db.execute(
                select(EncounterSetType)
                .options(selectinload(EncounterSetType.project), selectinload(EncounterSetType.target_scheme))
                .order_by(EncounterSetType.project_id, EncounterSetType.active.desc(), EncounterSetType.name)
            )
            .scalars()
            .all()
        ),
        "ai_models_by_disease": ai_models_by_disease,
        "upload_profiles": upload_profiles,
        "investigators": investigators,
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
        context["project_profiles"] = [
            profile for profile in context["upload_profiles"] if profile.project_id == project_id
        ]
        context["selected_profile_id"] = request.args.get("profile_id", type=int)
        return render_template("admin/partials/project_detail_panel.html", **context)


@roles_required("admin", "local_admin", "data_manager")
def upload_project_create_workspace():
    """Render project create workspace fragment."""
    scoped_lab_ids = _manager_lab_unit_ids()
    if not scoped_lab_ids:
        return render_template("admin/partials/project_create_panel.html"), 403
    return render_template("admin/partials/project_create_panel.html")
