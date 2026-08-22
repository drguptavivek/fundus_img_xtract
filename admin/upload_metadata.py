"""Admin pages for reusable upload metadata field masters."""
from __future__ import annotations

from flask import flash, redirect, render_template, url_for
from flask_login import current_user

from auth.roles import roles_required
from upload_metadata import service as upload_metadata_service
from upload_profiles.service import manager_lab_unit_ids


def _has_manager_scope() -> bool:
    return bool(manager_lab_unit_ids(current_user.id))


def _context() -> dict:
    return {
        "field_definitions": upload_metadata_service.list_field_definitions(current_user.id, include_inactive=True),
        "field_scopes": sorted(upload_metadata_service.SUPPORTED_FIELD_SCOPES),
        "field_types": sorted(upload_metadata_service.SUPPORTED_FIELD_TYPES),
    }


@roles_required("admin")
def upload_metadata_fields_admin():
    """Render reusable upload metadata field master UI."""
    if not _has_manager_scope():
        flash("You are not assigned to any lab units for upload metadata management.", "warning")
        return redirect(url_for("admin.users_list"))
    return render_template("admin/upload_metadata_fields.html", **_context())


@roles_required("admin")
def upload_metadata_fields_list():
    """Render upload metadata field master list partial."""
    if not _has_manager_scope():
        return render_template("admin/partials/upload_metadata_field_list.html", field_definitions=[]), 403
    return render_template(
        "admin/partials/upload_metadata_field_list.html",
        field_definitions=upload_metadata_service.list_field_definitions(current_user.id, include_inactive=True),
    )
