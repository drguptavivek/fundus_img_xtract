"""Admin pages for EncounterSetType configuration."""
from __future__ import annotations

from flask import flash, render_template, redirect, request, url_for
from flask_login import current_user
from sqlalchemy import select

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from encounter_set_types import service as encounter_set_type_service
from models import Disease
from upload_metadata import service as upload_metadata_service
from upload_profiles.service import manager_lab_unit_ids


def _has_manager_scope() -> bool:
    return bool(manager_lab_unit_ids(current_user.id))


def _context() -> dict:
    with transaction_scope() as db:
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        return {
            "diseases": [
                {
                    "id": disease.id,
                    "name": disease.name,
                    "grading_scope": disease.grading_scope,
                }
                for disease in diseases
            ],
            "encounter_set_types": encounter_set_type_service.list_encounter_set_types(
                current_user.id,
                include_inactive=True,
            ),
            "field_definitions": upload_metadata_service.list_field_definitions(current_user.id, include_inactive=False),
        }


def _render_workspace(workspace: str):
    context = _context()
    context["workspace"] = workspace
    if request.headers.get("HX-Request") == "true":
        return render_template("admin/partials/encounter_set_type_workspace.html", **context)
    return render_template("admin/encounter_set_types.html", **context)


@roles_required("admin")
def encounter_set_types_admin():
    """Render EncounterSetType configuration UI."""
    if not _has_manager_scope():
        flash("You are not assigned to any lab units for EncounterSetType management.", "warning")
        return redirect(url_for("admin.users_list"))
    return _render_workspace("list")


@roles_required("admin")
def encounter_set_types_list():
    """Render the EncounterSetType list partial for HTMX refreshes."""
    if not _has_manager_scope():
        return render_template("admin/partials/encounter_set_type_workspace.html", encounter_set_types=[], workspace="list"), 403
    return _render_workspace("list")


@roles_required("admin")
def encounter_set_type_new():
    """Render create workspace."""
    if not _has_manager_scope():
        flash("You are not assigned to any lab units for EncounterSetType management.", "warning")
        return redirect(url_for("admin.users_list"))
    return _render_workspace("new")


@roles_required("admin")
def encounter_set_type_edit(type_id: int):
    """Render edit workspace."""
    if not _has_manager_scope():
        flash("You are not assigned to any lab units for EncounterSetType management.", "warning")
        return redirect(url_for("admin.users_list"))
    result = encounter_set_type_service.get_encounter_set_type(current_user.id, type_id)
    if not result.success:
        return render_template("admin/partials/encounter_set_type_message.html", message=result.message, category="danger"), result.status_code
    context = _context()
    context["workspace"] = "edit"
    context["edit_encounter_set_type"] = result.payload["encounter_set_type"]
    if request.headers.get("HX-Request") == "true":
        return render_template("admin/partials/encounter_set_type_workspace.html", **context)
    return render_template("admin/encounter_set_types.html", **context)


@roles_required("admin")
def encounter_set_type_view(type_id: int):
    """Render read-only EncounterSetType detail workspace."""
    if not _has_manager_scope():
        flash("You are not assigned to any lab units for EncounterSetType management.", "warning")
        return redirect(url_for("admin.users_list"))
    result = encounter_set_type_service.get_encounter_set_type(current_user.id, type_id)
    if not result.success:
        return render_template("admin/partials/encounter_set_type_message.html", message=result.message, category="danger"), result.status_code
    context = _context()
    context["workspace"] = "view"
    context["edit_encounter_set_type"] = result.payload["encounter_set_type"]
    if request.headers.get("HX-Request") == "true":
        return render_template("admin/partials/encounter_set_type_workspace.html", **context)
    return render_template("admin/encounter_set_types.html", **context)
