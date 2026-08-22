"""Admin routes for projects and upload profiles."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from data_authorization.exceptions import ProjectAuthorizationError
from data_authorization.models import HOSPITAL_SCOPE, LAB_UNIT_SCOPE, PROJECT_SCOPE
from data_authorization.policy import (
    ACTION_MANAGE_ACCESS,
    ACTION_MANAGE_UPLOADERS,
    PROJECT_ADMIN_ASSIGNABLE_ROLE_NAMES,
    PROJECT_ASSIGNABLE_ROLE_NAMES,
    user_can_project_action,
)
from data_authorization.service import list_project_role_grants
from db_transaction_manager import transaction_scope
from grading_allocation import service as grading_allocation_service
from models import (
    Area,
    Camera,
    Disease,
    DiseaseGrading,
    EncounterSetType,
    LabUnit,
    LinkedDiseaseGrading,
    Project,
    ProjectInvestigator,
    Role,
    User,
)
from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding, RemidioApiSourceRule
from remote_inference.automated_service import project_automated_workflow_context
from remote_inference.manual_service import project_manual_workflow_context
from project_configuration.service import configured_project_lab_unit_ids
from remote_inference.encounter_service import workflow_context as encounter_workflow_context
from iitk_api_integration import service as iitk_service
from upload_profiles.service import manager_lab_unit_ids
from services.project_referral_diseases import list_configured_project_referral_disease_ids
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
            .where(User.is_active.is_(True))
            .options(selectinload(User.lab_units), selectinload(User.roles))
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
                selectinload(UploadProfile.encounter_set_types).selectinload(UploadProfileEncounterSetType.encounter_set_type),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.encounter_grading_scheme),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.encounter_grading_scheme)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.default_image_grading_scheme),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypeImageGradingScheme.disease),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypeImageGradingScheme.disease)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageImageScheme.disease),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageImageScheme.disease)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.encounter_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageEncounterScheme.disease),
                selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.encounter_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageEncounterScheme.disease)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
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
                .selectinload(UploadProfileEncounterSetType.encounter_grading_scheme)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.default_image_grading_scheme),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypeImageGradingScheme.disease),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypeImageGradingScheme.disease)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageImageScheme.disease),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageImageScheme.disease)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.encounter_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageEncounterScheme.disease),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.encounter_grading_schemes)
                .selectinload(UploadProfileEncounterSetTypePackageEncounterScheme.disease)
                .selectinload(Disease.disease_gradings)
                .selectinload(DiseaseGrading.features),
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
        "scope_hospitals": sorted(
            {lab_unit.hospital for lab_unit in lab_units},
            key=lambda hospital: hospital.name,
        ),
        "scoped_lab_ids": scoped_lab_ids,
        "users": users,
        "projects": projects,
        "project_cards": project_cards,
        "diseases": (
            db.execute(
                select(Disease)
                .options(selectinload(Disease.disease_gradings).selectinload(DiseaseGrading.features))
                .order_by(Disease.name)
            )
            .scalars()
            .unique()
            .all()
        ),
        "linked_disease_parent_by_child": {
            link.linked_disease_id: link.primary_disease_id
            for link in db.execute(
                select(LinkedDiseaseGrading).where(
                    LinkedDiseaseGrading.is_active.is_(True)
                )
            ).scalars().all()
        },
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


@roles_required("admin")
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


@login_required
def upload_projects_admin():
    """Render project and investigator governance."""
    with transaction_scope() as db:
        project_ids = _manageable_project_ids(db)
        if not project_ids:
            return render_template("admin/upload_projects.html", projects=[], projects_only=True), 403
        scoped_lab_ids = _manageable_project_lab_ids(db, project_ids)
        context = _mapping_form_context(db, scoped_lab_ids)
        context["projects"] = [project for project in context["projects"] if project.id in project_ids]
        context["project_cards"] = [
            card for card in context["project_cards"] if card["project"].id in project_ids
        ]
        context["project_profile_mappings"] = [
            mapping for mapping in context["project_profile_mappings"] if mapping.project_id in project_ids
        ]
        context["can_configure_project"] = current_user.has_role("admin")
        context["selected_project_id"] = request.args.get("project_id", type=int)
        context["projects_only"] = True
        return render_template("admin/upload_projects.html", **context)


@login_required
def upload_project_workspace(project_id: int):
    """Render one project management workspace fragment."""
    with transaction_scope() as db:
        can_manage_access = user_can_project_action(
            db, user=current_user, project_id=project_id, action=ACTION_MANAGE_ACCESS
        )
        can_manage_uploaders = user_can_project_action(
            db, user=current_user, project_id=project_id, action=ACTION_MANAGE_UPLOADERS
        )
        if not (can_manage_access or can_manage_uploaders):
            return render_template("admin/partials/project_detail_panel.html", selected_project=None), 403
        scoped_lab_ids = set(configured_project_lab_unit_ids(db, project_id=project_id))
        context = _mapping_form_context(db, scoped_lab_ids)
        selected_project = next((project for project in context["projects"] if project.id == project_id), None)
        if not selected_project:
            return render_template("admin/partials/project_detail_panel.html", selected_project=None), 404
        context["selected_project"] = selected_project
        context["can_configure_project"] = current_user.has_role("admin")
        context["can_manage_access"] = can_manage_access
        context["can_manage_uploaders"] = can_manage_uploaders
        context["configuration_lab_units"] = db.execute(
            select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.hospital_id, LabUnit.name)
        ).scalars().all()
        context["configured_project_lab_unit_ids"] = scoped_lab_ids
        context["project_profile_mappings"] = [
            mapping for mapping in context["project_profile_mappings"] if mapping.project_id == project_id
        ]
        context["enabled_profile_ids"] = {
            mapping.upload_profile_id for mapping in context["project_profile_mappings"] if mapping.active
        }
        context["selected_profile_id"] = request.args.get("profile_id", type=int)
        context["configured_referral_disease_ids"] = set(
            list_configured_project_referral_disease_ids(db, project_id=project_id)
        )
        try:
            grants = list_project_role_grants(db, actor=current_user, project_id=project_id)
        except ProjectAuthorizationError:
            grants = ()
        context["project_access_rows"] = _group_project_access_rows(grants)
        assignable_roles = (
            PROJECT_ASSIGNABLE_ROLE_NAMES
            if current_user.has_role("admin")
            else PROJECT_ADMIN_ASSIGNABLE_ROLE_NAMES
        )
        context["project_role_options"] = tuple(sorted(
            db.execute(
                select(Role).where(Role.name.in_(assignable_roles)).order_by(Role.name)
            ).scalars().all(),
            key=lambda role: role.name.lower(),
        ))
        context["project_assignable_role_names"] = assignable_roles
        for row in context["project_access_rows"]:
            row["editable"] = any(
                grant.role_name in assignable_roles for grant in row["grants"]
            )
        context.update(project_automated_workflow_context(db, project_id))
        context.update(project_manual_workflow_context(db, project_id))
        context["dr_dme_encounter_workflow"] = encounter_workflow_context(db, project_id)
        context.update(iitk_service.project_connection_context(db, project_id))
        context["grading_allocation_state"] = grading_allocation_service.get_project_allocation_state(
            current_user.id,
            project_id,
        )
        return render_template("admin/partials/project_detail_panel.html", **context)


def _group_project_access_rows(grants) -> list[dict]:
    """Group active role grants by user and exact project data scope."""
    rows: dict[tuple, dict] = {}
    for grant in grants:
        if not grant.active:
            continue
        key = (
            grant.user_id,
            grant.scope_type,
            grant.hospital_id,
            grant.lab_unit_id,
        )
        row = rows.setdefault(key, {
            "user_id": grant.user_id,
            "user_name": grant.user_name,
            "username": grant.username,
            "scope_type": grant.scope_type,
            "hospital_id": grant.hospital_id,
            "hospital_name": grant.hospital_name,
            "lab_unit_id": grant.lab_unit_id,
            "lab_unit_name": grant.lab_unit_name,
            "grants": [],
        })
        row["grants"].append(grant)
    for row in rows.values():
        row["grants"].sort(key=lambda grant: grant.role_name.lower())
        if row["scope_type"] == PROJECT_SCOPE:
            row["scope_label"] = "Project-wide"
        elif row["scope_type"] == HOSPITAL_SCOPE:
            row["scope_label"] = row["hospital_name"] or "Hospital"
        elif row["scope_type"] == LAB_UNIT_SCOPE:
            names = [name for name in (row["hospital_name"], row["lab_unit_name"]) if name]
            row["scope_label"] = " / ".join(names) or "Lab unit"
    return sorted(
        rows.values(),
        key=lambda row: (row["user_name"].lower(), row["scope_label"].lower()),
    )


@roles_required("admin")
def upload_project_create_workspace():
    """Render project create workspace fragment."""
    scoped_lab_ids = _manager_lab_unit_ids()
    if not scoped_lab_ids:
        return render_template("admin/partials/project_create_panel.html"), 403
    return render_template("admin/partials/project_create_panel.html")


def _manageable_project_ids(db) -> set[int]:
    if current_user.has_role("admin"):
        return set(db.execute(select(Project.id)).scalars())
    return {
        project_id
        for project_id in db.execute(select(Project.id).where(Project.active.is_(True))).scalars()
        if user_can_project_action(
            db,
            user=current_user,
            project_id=project_id,
            action=ACTION_MANAGE_ACCESS,
        )
    }


def _manageable_project_lab_ids(db, project_ids: set[int]) -> set[int]:
    allowed: set[int] = set()
    for project_id in project_ids:
        allowed.update(configured_project_lab_unit_ids(db, project_id=project_id))
    return allowed
