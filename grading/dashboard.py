
from flask import render_template, request, url_for, flash
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
    disease_queue_cards,
    project_encounter_set_cards,
)

 
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


@roles_required("ophthalmologist", "field_ophthalmologist")
def index():
    # Stats + most recent encounter with an ungraded glaucoma image
    with transaction_scope() as db:
        # The history panel sits below the fold: the full page paints a
        # placeholder that fetches it through this same route over HTMX.
        if request.headers.get("HX-Request") == "true":
            page = request.args.get('p', default=1, type=int) or 1
            try:
                history_panel_context = _build_history_panel_context(
                    db,
                    user_id=getattr(current_user, 'id', None),
                    page=max(1, page),
                    per_page=12,
                    filter_date=request.args.get('date', default=None, type=str),
                    history_type=request.args.get("history_type", default="all", type=str),
                    disease_id=request.args.get("disease_id", default=None, type=int),
                )
            except ValueError as exc:
                # A redirect here would make HTMX swap the whole page into the
                # panel; fall back to the default view of the panel instead.
                flash(str(exc), "warning")
                history_panel_context = _build_history_panel_context(
                    db,
                    user_id=getattr(current_user, 'id', None),
                    page=1,
                    per_page=12,
                    filter_date=None,
                    history_type="all",
                    disease_id=None,
                )
            return render_template("grading/_history_panel.html", **history_panel_context)

        # Queue cards, eligibility and history are fetched as HTMX fragments
        # (on load or on demand), so first paint only waits on this lookup.
        active_sessions = list_active_sessions(db, user_id=current_user.id)
        active_workbench = active_sessions[0] if active_sessions else None
    return render_template(
        "grading/index.html",
        refresh=False,
        oob=False,
        active_workbench=active_workbench,
    )


@roles_required("ophthalmologist", "field_ophthalmologist")
def eligibility_fragment():
    """The My Grading Eligibility panel, fetched on demand from the dashboard."""
    with transaction_scope() as db:
        eligibility = grader_eligibility_dto(db, user_id=current_user.id)
    return render_template(
        "grading/_eligibility_panel.html", grading_eligibility=eligibility
    )


@roles_required("ophthalmologist", "field_ophthalmologist")
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


@roles_required("ophthalmologist", "field_ophthalmologist")
def disease_queues_fragment():
    """The Legacy & Image Grading panel of self-loading placeholders.

    Used for the first paint. Refreshing does not come back through here: each
    rendered card re-fetches itself in place instead, so a refresh never
    reverts visible counts to placeholders.
    """
    refresh = request.args.get("refresh") == "1"
    with transaction_scope() as db:
        queue_cards = disease_queue_cards(
            db, user_id=current_user.id, refresh=refresh
        )
    return render_template(
        "grading/_disease_queues.html",
        queue_cards=queue_cards,
        refresh=refresh,
    )


@roles_required("ophthalmologist", "field_ophthalmologist")
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


@roles_required("ophthalmologist", "field_ophthalmologist")
def refresh_queues_trigger():
    """Fire the panel-wide refresh event; the panels re-fetch themselves.

    Returns no body. The ``HX-Trigger`` header lets every card and the project
    panel reload independently and in place, which avoids both a placeholder
    flash and any inline script to dispatch the event.
    """
    return "", 204, {"HX-Trigger": "refresh-queues"}
