"""Compatibility transports for EncounterSet package grading.

Package allocation, completeness, revision, submission, and state rules are
owned by ``grading.workbench``.
"""

from __future__ import annotations

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.workbench.errors import WorkbenchError
from grading.workbench.legacy_transport import submit_package_form
from grading.workbench_page import open_package_workbench


def register_routes(bp):
    bp.add_url_rule(
        "/encounter_set_package/<string:package_uuid>/<string:slot_type>",
        view_func=encounter_set_package_grading,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/encounter_set_package/submit",
        view_func=encounter_set_package_submit,
        methods=["POST"],
    )


@login_required
@roles_required("ophthalmologist")
def encounter_set_package_grading(package_uuid: str, slot_type: str):
    return open_package_workbench(package_uuid, slot_type)


@login_required
@roles_required("ophthalmologist")
def encounter_set_package_submit():
    try:
        with transaction_scope() as db:
            submit_package_form(db, user_id=current_user.id, form=request.form)
        flash("EncounterSet package submitted successfully.", "success")
    except WorkbenchError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("grading.index"))
