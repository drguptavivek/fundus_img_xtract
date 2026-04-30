"""Admin routes for project-scoped upload mappings."""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import (
    Area,
    Camera,
    Disease,
    LabUnit,
    Project,
    ProjectInvestigator,
    UploadMapping,
    UploadMappingArea,
    UploadMappingCamera,
    User,
    user_lab_units,
)
from utils.upload_scope import get_scoped_mapping_admin_lab_unit_ids


def _to_int(value: str | None) -> int | None:
    """Parse a form integer field, returning None when invalid."""
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _to_int_list(values: list[str]) -> list[int]:
    """Parse a list of form integer fields and skip invalid values."""
    parsed: list[int] = []
    for value in values:
        item = _to_int(value)
        if item is not None:
            parsed.append(item)
    return parsed


def _manager_lab_unit_ids() -> set[int]:
    """Return lab units the current manager can administer without overrides."""
    return get_scoped_mapping_admin_lab_unit_ids(current_user.id)


def _validate_mydriatic_flags(*, allow_mydriatic: bool, allow_non_mydriatic: bool, default_is_mydriatic: bool) -> str | None:
    """Return a user-facing validation error for invalid mydriatic flag combinations."""
    if not allow_mydriatic and not allow_non_mydriatic:
        return "Select at least one mydriatic scope."
    if default_is_mydriatic and not allow_mydriatic:
        return "Default cannot be mydriatic unless mydriatic uploads are allowed."
    if not default_is_mydriatic and not allow_non_mydriatic:
        return "Default cannot be non-mydriatic unless non-mydriatic uploads are allowed."
    return None


def _mapping_form_context(db, scoped_lab_ids: set[int]) -> dict:
    """Build detached-safe context for upload mapping management templates."""
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
    mappings = (
        db.execute(
            select(UploadMapping)
            .where(UploadMapping.lab_unit_id.in_(scoped_lab_ids))
            .options(
                selectinload(UploadMapping.user),
                selectinload(UploadMapping.project),
                selectinload(UploadMapping.lab_unit),
                selectinload(UploadMapping.disease),
                selectinload(UploadMapping.default_disease),
                selectinload(UploadMapping.cameras).selectinload(UploadMappingCamera.camera),
                selectinload(UploadMapping.areas).selectinload(UploadMappingArea.area),
            )
            .order_by(UploadMapping.active.desc(), UploadMapping.project_id, UploadMapping.user_id)
        )
        .scalars()
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
        project_cards.append(
            {
                "project": project,
                "investigator_count": sum(
                    1 for investigator in investigators if investigator.project_id == project.id and investigator.active
                ),
                "mapping_count": sum(
                    1 for mapping in mappings if mapping.project_id == project.id and mapping.active
                ),
                "uploader_count": len(
                    {
                        mapping.user_id
                        for mapping in mappings
                        if mapping.project_id == project.id and mapping.active
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
        "mappings": mappings,
        "investigators": investigators,
    }


@roles_required("admin", "local_admin", "data_manager")
def upload_mappings_admin():
    """Render the project dashboard and handle HTMX project/upload actions."""
    scoped_lab_ids = _manager_lab_unit_ids()
    if not scoped_lab_ids:
        flash("You are not assigned to any lab units for upload mapping management.", "warning")
        return redirect(url_for("admin.users_list"))

    with transaction_scope() as db:
        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "create_project":
                    title = (request.form.get("title") or "").strip()
                    code = (request.form.get("code") or "").strip().upper()
                    description = (request.form.get("description") or "").strip() or None
                    if not title or not code:
                        flash("Project title and code are required.", "danger")
                    else:
                        db.add(Project(title=title, code=code, description=description, active=True))
                        flash("Project created.", "success")

                elif action == "add_investigator":
                    project_id = _to_int(request.form.get("project_id"))
                    user_id = _to_int(request.form.get("user_id"))
                    role = request.form.get("role") or "co_investigator"
                    if not project_id or not user_id:
                        flash("Project and investigator are required.", "danger")
                    else:
                        db.add(ProjectInvestigator(project_id=project_id, user_id=user_id, role=role, active=True))
                        flash("Project investigator added.", "success")

                elif action == "create_mapping":
                    user_id = _to_int(request.form.get("user_id"))
                    lab_unit_id = _to_int(request.form.get("lab_unit_id"))
                    project_id = _to_int(request.form.get("project_id"))
                    disease_id = _to_int(request.form.get("disease_id"))
                    default_disease_id = _to_int(request.form.get("default_disease_id"))
                    camera_ids = _to_int_list(request.form.getlist("camera_ids"))
                    area_ids = _to_int_list(request.form.getlist("area_ids"))
                    allow_mydriatic = request.form.get("allow_mydriatic") == "on"
                    allow_non_mydriatic = request.form.get("allow_non_mydriatic") == "on"
                    default_is_mydriatic = request.form.get("default_is_mydriatic") == "on"
                    mydriatic_error = _validate_mydriatic_flags(
                        allow_mydriatic=allow_mydriatic,
                        allow_non_mydriatic=allow_non_mydriatic,
                        default_is_mydriatic=default_is_mydriatic,
                    )

                    if not all([user_id, lab_unit_id, project_id, disease_id]) or not camera_ids or not area_ids:
                        flash("Uploader, lab unit, project, disease, cameras, and sites are required.", "danger")
                    elif lab_unit_id not in scoped_lab_ids:
                        flash("You cannot create mappings outside your assigned lab units.", "danger")
                    elif mydriatic_error:
                        flash(mydriatic_error, "danger")
                    else:
                        user_lab_ids = {
                            row[0]
                            for row in db.execute(
                                select(user_lab_units.c.lab_unit_id).where(user_lab_units.c.user_id == user_id)
                            ).all()
                        }
                        if lab_unit_id not in user_lab_ids:
                            flash("The selected uploader is not assigned to that lab unit.", "danger")
                        else:
                            mapping = UploadMapping(
                                user_id=user_id,
                                lab_unit_id=lab_unit_id,
                                project_id=project_id,
                                disease_id=disease_id,
                                default_disease_id=default_disease_id,
                                allow_mydriatic=allow_mydriatic,
                                allow_non_mydriatic=allow_non_mydriatic,
                                default_is_mydriatic=default_is_mydriatic,
                                active=True,
                            )
                            mapping.cameras = [UploadMappingCamera(camera_id=camera_id) for camera_id in camera_ids]
                            mapping.areas = [UploadMappingArea(area_id=area_id) for area_id in area_ids]
                            db.add(mapping)
                            flash("Upload mapping created.", "success")
                else:
                    flash("Unknown upload mapping action.", "danger")
            except IntegrityError:
                db.rollback()
                flash("Duplicate or invalid project/mapping configuration.", "danger")
            if request.headers.get("HX-Request"):
                context = _mapping_form_context(db, scoped_lab_ids)
                return render_template("admin/partials/project_dashboard_workspace.html", **context)
            return redirect(url_for("admin.upload_mappings_admin"))

        context = _mapping_form_context(db, scoped_lab_ids)
        return render_template("admin/upload_mappings.html", **context)


@roles_required("admin", "local_admin", "data_manager")
def deactivate_upload_mapping(mapping_id: int):
    """Deactivate an upload mapping within the manager's explicit lab scope."""
    scoped_lab_ids = _manager_lab_unit_ids()
    with transaction_scope() as db:
        mapping = db.get(UploadMapping, mapping_id)
        if not mapping or mapping.lab_unit_id not in scoped_lab_ids:
            flash("Upload mapping not found in your lab-unit scope.", "danger")
        else:
            mapping.active = False
            flash("Upload mapping deactivated.", "success")
    return redirect(url_for("admin.upload_mappings_admin"))
