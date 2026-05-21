"""Admin pages for EncounterSetType configuration."""
from __future__ import annotations

from flask import flash, render_template, redirect, url_for
from flask_login import current_user
from sqlalchemy import select

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from encounter_set_types import service as encounter_set_type_service
from models import Disease, Project
from upload_profiles.service import manager_lab_unit_ids


def _has_manager_scope() -> bool:
    return bool(manager_lab_unit_ids(current_user.id))


def _context() -> dict:
    with transaction_scope() as db:
        return {
            "projects": db.execute(select(Project).where(Project.active.is_(True)).order_by(Project.title)).scalars().all(),
            "diseases": db.execute(select(Disease).order_by(Disease.name)).scalars().all(),
            "encounter_set_types": encounter_set_type_service.list_encounter_set_types(
                current_user.id,
                include_inactive=True,
            ),
        }


@roles_required("admin", "local_admin", "data_manager")
def encounter_set_types_admin():
    """Render EncounterSetType configuration UI."""
    if not _has_manager_scope():
        flash("You are not assigned to any lab units for EncounterSetType management.", "warning")
        return redirect(url_for("admin.users_list"))
    return render_template("admin/encounter_set_types.html", **_context())


@roles_required("admin", "local_admin", "data_manager")
def encounter_set_types_list():
    """Render the EncounterSetType list partial for HTMX refreshes."""
    if not _has_manager_scope():
        return render_template("admin/partials/encounter_set_type_list.html", encounter_set_types=[]), 403
    return render_template(
        "admin/partials/encounter_set_type_list.html",
        encounter_set_types=encounter_set_type_service.list_encounter_set_types(current_user.id, include_inactive=True),
    )
