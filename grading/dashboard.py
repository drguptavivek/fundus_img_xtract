from collections.abc import Mapping

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, desc, distinct, func


from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.dashboard_service import grader_eligibility_dto, grading_history_page
from grading.workbench.service import list_active_sessions
from models import PatientEncounters, EncounterFile, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User, Grade
from grading.queue_cards import (
    disease_queue_card,
    gradable_disease_cards,
    project_encounter_set_cards,
)
from utils.dualGradingEligibility import get_user_grading_eligibility_details

 
def _build_history_panel_context(
    db,
    *,
    user_id: int | None,
    page: int,
    per_page: int,
    filter_date: str | None,
    history_type: str,
    disease_id: int | None,
):
    history = grading_history_page(
        db,
        user_id=user_id,
        requested_date=filter_date,
        history_type=history_type,
        disease_id=disease_id,
        page=page,
        per_page=per_page,
    )
    def history_url(*, selected_date=None, selected_page=1):
        params = {
            "date": selected_date or history.selected_date,
            "history_type": history.history_type,
        }
        if history.disease_id:
            params["disease_id"] = history.disease_id
        if selected_page > 1:
            params["p"] = selected_page
        return url_for("grading.index", **params)

    return {
        "history": history.to_dict(),
        "my_prev_url": (
            history_url(selected_date=history.previous_date)
            if history.previous_date else None
        ),
        "my_next_url": (
            history_url(selected_date=history.next_date)
            if history.next_date else None
        ),
        "page_prev_url": (
            history_url(selected_page=history.page - 1)
            if history.page > 1 else None
        ),
        "page_next_url": (
            history_url(selected_page=history.page + 1)
            if history.page < history.total_pages else None
        ),
    }


@roles_required("ophthalmologist")
def index():
    # Stats + most recent encounter with an ungraded glaucoma image
    with transaction_scope() as db:
        page = request.args.get('p', default=1, type=int) or 1
        page = max(1, page)
        per_page = 12
        filter_date = request.args.get('date', default=None, type=str)
        history_type = request.args.get("history_type", default="all", type=str)
        disease_id = request.args.get("disease_id", default=None, type=int)
        try:
            history_panel_context = _build_history_panel_context(
                db,
                user_id=getattr(current_user, 'id', None),
                page=page,
                per_page=per_page,
                filter_date=filter_date,
                history_type=history_type,
                disease_id=disease_id,
            )
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("grading.index"))

        if request.headers.get("HX-Request") == "true":
            return render_template("grading/_history_panel.html", **history_panel_context)

        # Get dual grading tasks for the current user, separated by disease
        # and role (resident vs resident2) and arbitration tasks
        
        # Get user role to determine which tasks to show
        # For dual grading, determine eligibility based on user's eligibility matrix rather than specific 'resident' role
        # Any user with role that allows them to grade (resident, ophthalmologist) can do resident grading
        raw_user_eligibility = get_user_grading_eligibility_details(db, current_user.id)
        eligibility = grader_eligibility_dto(db, user_id=current_user.id)
        user_eligibility: dict[str, dict[str, dict[str, list[str]]]] = {}
        if isinstance(raw_user_eligibility, Mapping):
            for hospital_name, lab_units in raw_user_eligibility.items():
                normalized_lab_units: dict[str, dict[str, list[str]]] = {}
                if not isinstance(lab_units, Mapping):
                    continue
                for lab_unit_name, diseases in lab_units.items():
                    normalized_diseases: dict[str, list[str]] = {}
                    if not isinstance(diseases, Mapping):
                        continue
                    for disease_name, roles in diseases.items():
                        seen_roles: set[str] = set()
                        display_roles: list[str] = []
                        if isinstance(roles, (list, tuple, set)):
                            iterable_roles = roles
                        else:
                            iterable_roles = [roles]
                        for role in iterable_roles:
                            if not isinstance(role, str):
                                continue
                            role_lower = role.lower()
                            if role_lower in {"resident", "resident2"}:
                                display_role = "Resident"
                            else:
                                display_role = role.capitalize() if role.islower() else role
                            key = display_role.lower()
                            if key not in seen_roles:
                                seen_roles.add(key)
                                display_roles.append(display_role)
                        normalized_diseases[disease_name] = display_roles
                    normalized_lab_units[lab_unit_name] = normalized_diseases
                user_eligibility[hospital_name] = normalized_lab_units
        else:
            user_eligibility = {}

        # Check if user has any resident eligibility
        has_resident_eligibility = False
        for hospital_data in user_eligibility.values():
            for lab_unit_data in hospital_data.values():
                for diseases_roles in lab_unit_data.values():
                    if 'Resident' in diseases_roles:
                        has_resident_eligibility = True
                        break
                if has_resident_eligibility:
                    break
            if has_resident_eligibility:
                break
        
        # is_resident means user has permission to do resident-level grading
        is_resident = has_resident_eligibility and (current_user.has_role('resident') or current_user.has_role('ophthalmologist'))
        is_resident2 = current_user.has_role('ophthalmologist')
        
        # Which queue cards exist is answered from role rows alone. Their
        # contents are fetched per disease afterwards, so rendering this page
        # no longer waits on a sweep of the whole pending queue.
        project_encounter_set_queues = project_encounter_set_cards(
            db, user_id=current_user.id
        )
        active_sessions = list_active_sessions(db, user_id=current_user.id)
        active_workbench = active_sessions[0] if active_sessions else None
    return render_template(
        "grading/index.html",
        is_resident=is_resident,
        is_resident2=is_resident2,
        refresh=False,
        oob=False,
        user_eligibility=user_eligibility,
        grading_eligibility=eligibility,
        project_encounter_set_queues=project_encounter_set_queues,
        active_workbench=active_workbench,
        **history_panel_context,
    )


@roles_required("ophthalmologist")
def disease_queue_fragment(disease_id: int):
    """HTMX fragment for one disease queue card.

    The dashboard paints a placeholder per disease and swaps this in, so a slow
    disease delays only its own card instead of the whole page. Mirrors
    ``GET /api/grading/me/queues/<disease_id>`` from the same service call.

    ``?refresh=1`` is retained for the existing HTMX refresh contract.
    """
    refresh = request.args.get("refresh") == "1"
    with transaction_scope() as db:
        card = disease_queue_card(
            db,
            user_id=current_user.id,
            disease_id=disease_id,
            refresh=refresh,
        )
    return render_template(
        "grading/_disease_queue_card.html", card=card, refresh=refresh
    )


@roles_required("ophthalmologist")
def disease_queues_fragment():
    """The Legacy & Image Grading panel of self-loading placeholders.

    Used for the first paint. Refreshing does not come back through here: each
    rendered card re-fetches itself in place instead, so a refresh never
    reverts visible counts to placeholders.
    """
    refresh = request.args.get("refresh") == "1"
    with transaction_scope() as db:
        queue_cards = [
            card
            for card in (
                disease_queue_card(
                    db,
                    user_id=current_user.id,
                    disease_id=disease["id"],
                    refresh=refresh,
                )
                for disease in gradable_disease_cards(db, user_id=current_user.id)
            )
            if card is not None
        ]
    return render_template(
        "grading/_disease_queues.html",
        queue_cards=queue_cards,
        refresh=refresh,
    )


@roles_required("ophthalmologist")
def project_queues_fragment():
    """The Project EncounterSet Grading panel on its own, for in-place refresh."""
    refresh = request.args.get("refresh") == "1"
    with transaction_scope() as db:
        project_queues = project_encounter_set_cards(
            db, user_id=current_user.id, refresh=refresh
        )
    return render_template(
        "grading/_project_encounter_set_queues.html",
        project_encounter_set_queues=project_queues,
    )


@roles_required("ophthalmologist")
def refresh_queues_trigger():
    """Fire the panel-wide refresh event; the panels re-fetch themselves.

    Returns no body. The ``HX-Trigger`` header lets every card and the project
    panel reload independently and in place, which avoids both a placeholder
    flash and any inline script to dispatch the event.
    """
    return "", 204, {"HX-Trigger": "refresh-queues"}
