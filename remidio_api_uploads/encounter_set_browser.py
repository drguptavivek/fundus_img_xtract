from __future__ import annotations

from io import BytesIO
from datetime import datetime
from pathlib import Path

from flask import abort, render_template, request, send_file, url_for
from flask_login import current_user

from auth.roles import ROLE_COLLABORATOR, roles_required
from db_transaction_manager import get_db_session
from encounter_sets.access import ENCOUNTER_SET_PII_ROLES
from encounter_sets.models import EncounterSetAttachment
from encounter_sets.permissions import CAPABILITY_BROWSE, apply_project_permission_scope
from models import BASE_DIR, PatientEncounters
from remidio_api_integration import service as remidio_service
from utils.hospital_scoping import apply_scoping

from . import bp


BROWSER_ROLES = ENCOUNTER_SET_PII_ROLES
COLLABORATOR_BROWSER_ROLES = (ROLE_COLLABORATOR, "collaborators")


@bp.route("/uploads/encountersets/browse", methods=["GET"])
@roles_required(*BROWSER_ROLES)
def encounter_set_browser():
    context = _browser_context()
    return render_template("remidio_api_uploads/encounter_set_browser.html", **context)


@bp.route("/uploads/encountersets/browse/workspace", methods=["GET"])
@roles_required(*BROWSER_ROLES)
def encounter_set_browser_workspace():
    context = _browser_context()
    return render_template("remidio_api_uploads/_encounter_set_browser_workspace.html", **context)


@bp.route("/uploads/encountersets/browse-no-pii", methods=["GET"])
@roles_required(*COLLABORATOR_BROWSER_ROLES)
def encounter_set_browser_no_pii():
    context = _browser_context(no_pii=True)
    return render_template("remidio_api_uploads/encounter_set_browser_no_pii.html", **context)


@bp.route("/uploads/encountersets/browse-no-pii/workspace", methods=["GET"])
@roles_required(*COLLABORATOR_BROWSER_ROLES)
def encounter_set_browser_no_pii_workspace():
    context = _browser_context(no_pii=True)
    return render_template("remidio_api_uploads/_encounter_set_browser_workspace_no_pii.html", **context)


@bp.route("/uploads/encountersets/browse-no-pii/<int:encounter_id>/download", methods=["GET"])
@roles_required(*COLLABORATOR_BROWSER_ROLES)
def encounter_set_browser_no_pii_download(encounter_id: int):
    with get_db_session() as db:
        result = remidio_service.build_no_pii_encounter_set_zip(
            db,
            user=current_user,
            encounter_id=encounter_id,
        )
    if result is None:
        abort(404)
    content, filename = result
    response = send_file(
        BytesIO(content),
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/uploads/encountersets/attachments/<uuid>", methods=["GET"])
@roles_required(*BROWSER_ROLES)
def encounter_set_attachment(uuid: str):
    with get_db_session() as db:
        query = (
            db.query(EncounterSetAttachment)
            .join(PatientEncounters, EncounterSetAttachment.patient_encounter_id == PatientEncounters.id)
            .filter(EncounterSetAttachment.uuid == uuid)
        )
        query = apply_scoping(query, PatientEncounters, current_user, "upload")
        query = apply_project_permission_scope(query, PatientEncounters, current_user, CAPABILITY_BROWSE)
        attachment = query.first()
        if not attachment or not attachment.folder_rel or not attachment.stored_filename:
            abort(404)
        path = (BASE_DIR / Path(attachment.folder_rel) / attachment.stored_filename).resolve()
        if not path.exists() or not path.is_file():
            abort(404)
        return send_file(
            path,
            mimetype=attachment.mime_type or "application/octet-stream",
            as_attachment=False,
            download_name=attachment.original_filename,
        )


def _browser_context(*, no_pii: bool = False) -> dict:
    project_id = _optional_int(request.args.get("project_id"))
    selected_date = _optional_date(request.args.get("date"))
    selected_month = _optional_month(request.args.get("month"))
    encounter_id = _optional_int(request.args.get("encounter_id"))
    with get_db_session() as db:
        context = remidio_service.list_encounter_set_browser(
            db,
            user=current_user,
            project_id=project_id,
            selected_date=selected_date,
            selected_month=selected_month,
            encounter_id=encounter_id,
            no_pii=no_pii,
        )
    context["browser_url"] = _browser_url(context, no_pii=no_pii)
    context["browser_workspace_endpoint"] = (
        "remidio_api_uploads.encounter_set_browser_no_pii_workspace"
        if no_pii
        else "remidio_api_uploads.encounter_set_browser_workspace"
    )
    return context


def _browser_url(context: dict, *, no_pii: bool = False) -> str:
    params = {}
    if context.get("selected_project_id"):
        params["project_id"] = context["selected_project_id"]
    if context.get("selected_month"):
        params["month"] = context["selected_month"]
    if context.get("selected_date"):
        params["date"] = context["selected_date"].isoformat()
    if context.get("selected_encounter_id"):
        params["encounter_id"] = context["selected_encounter_id"]
    endpoint = "remidio_api_uploads.encounter_set_browser_no_pii" if no_pii else "remidio_api_uploads.encounter_set_browser"
    return url_for(endpoint, **params)


def _optional_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_date(value: str | None):
    if value in {None, ""}:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _optional_month(value: str | None) -> str | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.strptime(str(value), "%Y-%m")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m")
