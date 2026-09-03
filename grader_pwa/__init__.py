"""Grader PWA: an installable, same-origin grading client served under ``/grader``.

The PWA is a set of thin page routes over the existing grading services and the
JSON workbench API. It renders the same workbench body partial as the web page
(``grading/_workbench_body.html``) inside a chrome-less dark layout, so image
filters, grade capture and annotation behave identically on every platform.

Public (pre-login) surface: the manifest, the service worker and the offline
page. Everything else requires a grading role and the normal session cookie;
Flask-Login sends anonymous visitors to ``/login?next=...`` so direct links
land back on the requested case after sign-in.
"""

from __future__ import annotations

from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from auth.decorators import grading_reauth_gate
from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.dashboard_service import grading_history_page
from grading.queue_cards import disease_queue_card, grader_queue_overview
from grading.workbench.service import list_active_sessions
from grader_pwa.demo import build_demo_workbench
from grading.workbench_page import (
    open_linked_followup_workbench,
    open_next_workbench,
    open_package_workbench,
    open_revision_workbench,
    open_task_workbench,
    render_workbench_page,
)

bp = Blueprint("grader_pwa", __name__, url_prefix="/grader")

GRADING_ROLES = ("ophthalmologist", "field_ophthalmologist")
ROLE_SLOTS = frozenset({"resident", "resident2", "arbitrator"})
HISTORY_PER_PAGE = 20

# Mirrors ``--bs-body-bg`` of the dark Bootstrap build (static/css/bootstrap.min.css)
# so the splash and title bar match the page; the viewer stage itself stays black.
THEME_COLOR = "#151c20"


def _endpoints() -> dict[str, str]:
    return {
        "workbench_endpoint": "grader_pwa.workbench",
        "fallback_endpoint": "grader_pwa.home",
    }


def workbench_url_template() -> str:
    """``/grader/workbench/{uuid}`` for the session controller's save-and-next hop."""
    return url_for("grader_pwa.workbench", session_uuid="__uuid__").replace(
        "__uuid__", "{uuid}"
    )


def shell_assets() -> dict[str, str]:
    """Every static file the app shell needs, versioned exactly as the layout links them.

    One source for both the layout and the service worker precache list, so a
    version bump can never leave the worker caching a URL the pages no longer use.
    """
    version = current_app.config.get("ASSETS_VERSION", "") or ""
    pwa_version = f"{version}-grader-pwa-v5"

    def static(filename: str, v: str = version) -> str:
        return url_for("static", filename=filename, v=v)

    return {
        "bootstrap_css": static("css/bootstrap.min.css"),
        "fontawesome_css": static("css/fa_7.0.1.all.min.css"),
        "app_css": static("css/app.css"),
        "workbench_css": static("css/grading-workbench.css", f"{version}-workbench-css-v1"),
        "pwa_css": static("css/grader-pwa.css", pwa_version),
        "bootstrap_js": static("js/bootstrap.bundle.min.js"),
        "flash_toasts_js": static("js/flash-toasts.js"),
        "pwa_js": static("js/grader-pwa.js", pwa_version),
        "webauthn_js": static("js/webauthn.js", pwa_version),
        "auth_js": static("js/grader-auth.js", pwa_version),
        "logo": static("retina_svg_logo.svg"),
        "icon_192": static("grader-pwa/icons/icon-192.png"),
        "icon_512": static("grader-pwa/icons/icon-512.png"),
        "icon_maskable_192": static("grader-pwa/icons/icon-maskable-192.png"),
        "icon_maskable_512": static("grader-pwa/icons/icon-maskable-512.png"),
    }


@bp.context_processor
def _pwa_context():
    return {
        "pwa_assets": shell_assets(),
        "pwa_theme_color": THEME_COLOR,
        "pwa_manifest_url": url_for("grader_pwa.manifest"),
        "pwa_sw_url": url_for("grader_pwa.service_worker"),
        "pwa_scope": url_for("grader_pwa.home"),
    }


# --------------------------------------------------------------------------- #
# Public install surface
# --------------------------------------------------------------------------- #


@bp.get("/manifest.webmanifest")
def manifest():
    assets = shell_assets()
    payload = {
        "id": url_for("grader_pwa.home"),
        "name": "Eye Image Manager Grader",
        "short_name": "Grader",
        "description": "Log in and grade fundus images from your phone, tablet or desktop.",
        "start_url": url_for("grader_pwa.home", source="pwa"),
        "scope": url_for("grader_pwa.home"),
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "orientation": "any",
        "background_color": THEME_COLOR,
        "theme_color": THEME_COLOR,
        "lang": "en",
        "icons": [
            {"src": assets["icon_192"], "sizes": "192x192", "type": "image/png"},
            {"src": assets["icon_512"], "sizes": "512x512", "type": "image/png"},
            {"src": assets["icon_maskable_192"], "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": assets["icon_maskable_512"], "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "launch_handler": {"client_mode": "navigate-existing"},
        "shortcuts": [
            {"name": "My queues", "url": url_for("grader_pwa.home")},
            {"name": "History", "url": url_for("grader_pwa.history")},
        ],
    }
    response = jsonify(payload)
    response.mimetype = "application/manifest+json"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@bp.get("/sw.js")
def service_worker():
    assets = shell_assets()
    precache = [url_for("grader_pwa.offline")] + sorted(set(assets.values()))
    body = render_template(
        "grader_pwa/sw.js",
        shell_assets=precache,
        offline_url=url_for("grader_pwa.offline"),
        scope=url_for("grader_pwa.home"),
        login_url=url_for("grader_pwa.login"),
        mobile_refresh_url=url_for("mobile_api.refresh"),
    )
    response = make_response(body)
    response.mimetype = "application/javascript"
    # The worker must always be revalidated so a deploy reaches installed apps.
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = url_for("grader_pwa.home")
    return response


@bp.get("/offline")
def offline():
    return render_template("grader_pwa/offline.html")


@bp.get("/login")
def login():
    """Token sign-in (and re-authentication after inactivity) for the grader.

    Public: it renders no data. The page calls the mobile auth API with
    platform "web", stores the tokens, and hands them to the service worker.
    """
    next_url = request.args.get("next") or url_for("grader_pwa.home")
    if not next_url.startswith("/grader/"):
        next_url = url_for("grader_pwa.home")
    response = make_response(
        render_template(
            "grader_pwa/login.html",
            next_url=next_url,
            reauth=bool(request.args.get("reauth")),
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/demo")
def demo_page():
    """Public demo: the real workbench over a synthetic encounter set; nothing is saved."""
    with transaction_scope() as db:
        workbench = build_demo_workbench(db).to_dict()
    response = make_response(
        render_template(
            "grader_pwa/workbench.html",
            workbench=workbench,
            session_token="demo",
            submission_idempotency_key=str(uuid4()),
            workbench_dashboard_url=url_for("grader_pwa.demo_page"),
            workbench_url_template=None,
            demo=True,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------- #
# Authenticated pages
# --------------------------------------------------------------------------- #


@bp.get("/")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def home():
    with transaction_scope() as db:
        overview = grader_queue_overview(db, user_id=current_user.id)
        queues = []
        for disease in overview["legacy_diseases"]:
            card = disease_queue_card(db, user_id=current_user.id, disease_id=disease["id"])
            if card:
                queues.append(card)
        project_queues = overview["project_encounter_sets"]
        sessions = list_active_sessions(db, user_id=current_user.id)
    response = make_response(
        render_template(
            "grader_pwa/home.html",
            queues=queues,
            project_queues=project_queues,
            sessions=sessions,
        )
    )
    response.headers["Cache-Control"] = "no-store, private"
    return response


@bp.get("/start/<int:disease_id>/<string:role_slot>")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def start(disease_id: int, role_slot: str):
    if role_slot not in ROLE_SLOTS:
        flash("Invalid role slot.", "danger")
        return redirect(url_for("grader_pwa.home"))
    return open_next_workbench(
        disease_id,
        role_slot,
        lab_unit_id=request.args.get("lab_unit_id", type=int),
        **_endpoints(),
    )


@bp.get("/linked-followup/<int:primary_disease_id>/<int:linked_disease_id>")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def linked_followup(primary_disease_id: int, linked_disease_id: int):
    return open_linked_followup_workbench(primary_disease_id, linked_disease_id, **_endpoints())


@bp.get("/open/task/<string:task_uuid>/<string:role_slot>")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def open_task(task_uuid: str, role_slot: str):
    """Direct link into one task (the shareable URL for a case)."""
    if role_slot not in ROLE_SLOTS:
        flash("Invalid role slot.", "danger")
        return redirect(url_for("grader_pwa.home"))
    return open_task_workbench(task_uuid, role_slot, **_endpoints())


@bp.get("/open/package/<string:package_uuid>/<string:role_slot>")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def open_package(package_uuid: str, role_slot: str):
    if role_slot not in ROLE_SLOTS:
        flash("Invalid role slot.", "danger")
        return redirect(url_for("grader_pwa.home"))
    return open_package_workbench(package_uuid, role_slot, **_endpoints())


@bp.get("/open/grade/<int:grade_id>")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def open_grade_revision(grade_id: int):
    return open_revision_workbench(grade_id, **_endpoints())


@bp.get("/resume/<string:session_uuid>")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def resume(session_uuid: str):
    return redirect(url_for("grader_pwa.workbench", session_uuid=session_uuid))


@bp.get("/workbench/<string:session_uuid>")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def workbench(session_uuid: str):
    return render_workbench_page(
        session_uuid,
        template="grader_pwa/workbench.html",
        fallback_endpoint="grader_pwa.home",
        workbench_dashboard_url=url_for("grader_pwa.home"),
        workbench_url_template=workbench_url_template(),
    )


@bp.get("/history")
@roles_required(*GRADING_ROLES)
@grading_reauth_gate
def history():
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    try:
        with transaction_scope() as db:
            history_page = grading_history_page(
                db,
                user_id=current_user.id,
                requested_date=request.args.get("date") or None,
                history_type=request.args.get("type") or "all",
                disease_id=request.args.get("disease_id", type=int),
                page=page,
                per_page=HISTORY_PER_PAGE,
            )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("grader_pwa.history"))
    response = make_response(render_template("grader_pwa/history.html", history=history_page))
    response.headers["Cache-Control"] = "no-store, private"
    return response
