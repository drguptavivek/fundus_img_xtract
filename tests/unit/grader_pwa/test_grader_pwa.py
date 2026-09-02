"""Grader PWA: install surface, auth gating, and the shared-workbench contract."""
from __future__ import annotations

import json
import re
from inspect import unwrap
from pathlib import Path
from types import SimpleNamespace

from flask import session as flask_session

import grader_pwa
import grading.workbench_page as workbench_page

ROOT = Path(__file__).resolve().parents[3]


def _referenced_filter_ids() -> set[str]:
    """Every SVG filter id the viewer or the stylesheet applies with url(#...)."""
    sources = (ROOT / "static/js/grading-viewer.js", ROOT / "static/css/app.css")
    ids = set()
    for source in sources:
        ids.update(re.findall(r"url\(#(pswp-[a-z0-9-]+)\)", source.read_text()))
    assert ids, "expected the viewer to reference at least one SVG filter"
    return ids


# --------------------------------------------------------------------------- #
# Public install surface
# --------------------------------------------------------------------------- #


def test_manifest_is_public_and_scoped_to_grader(client):
    response = client.get("/grader/manifest.webmanifest")

    assert response.status_code == 200
    assert response.mimetype == "application/manifest+json"
    manifest = json.loads(response.data)
    assert manifest["scope"] == "/grader/"
    assert manifest["start_url"].startswith("/grader/")
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == manifest["background_color"] == "#151c20"
    purposes = {icon.get("purpose", "any") for icon in manifest["icons"]}
    assert {"any", "maskable"} <= purposes
    for icon in manifest["icons"]:
        relative = icon["src"].split("?", 1)[0].removeprefix("/static/")
        assert (ROOT / "static" / relative).is_file(), icon["src"]


def test_service_worker_is_public_scoped_and_caches_shell_only(client):
    response = client.get("/grader/sw.js")

    assert response.status_code == 200
    assert response.mimetype == "application/javascript"
    assert response.headers["Service-Worker-Allowed"] == "/grader/"
    assert response.headers["Cache-Control"] == "no-cache"
    body = response.get_data(as_text=True)
    assert '"/grader/offline"' in body
    # Only versioned static files may be cached; API, media and pages are network-only.
    assert "url.pathname.startsWith('/static/')" in body
    assert "request.mode === 'navigate'" in body
    assert "/api/" not in json.loads(re.search(r"const SHELL_ASSETS = (\[.*?\]);", body, re.S).group(1)).__str__()


def test_offline_page_is_public(client):
    response = client.get("/grader/offline")

    assert response.status_code == 200
    assert "offline" in response.get_data(as_text=True).lower()


def test_pwa_layout_carries_every_viewer_filter_definition(client):
    """A chrome-less shell that dropped base.html's <defs> would silently render
    every filter as a no-op; both hosts must define every id the viewer uses."""
    ids = _referenced_filter_ids()

    pwa_page = client.get("/grader/offline").get_data(as_text=True)
    web_page = client.get("/login").get_data(as_text=True)

    for filter_id in ids:
        assert f'id="{filter_id}"' in pwa_page, f"{filter_id} missing from the PWA layout"
        assert f'id="{filter_id}"' in web_page, f"{filter_id} missing from base.html"
        assert f'id="{filter_id}" color-interpolation-filters="sRGB"' in pwa_page


# --------------------------------------------------------------------------- #
# Authentication and roles
# --------------------------------------------------------------------------- #


def test_anonymous_visitor_is_sent_to_login(client):
    for path in ("/grader/", "/grader/history", "/grader/workbench/abc", "/grader/start/1/resident"):
        response = client.get(path)
        assert response.status_code in (302, 308), path
        assert "/login" in response.headers["Location"], path


def test_home_is_forbidden_without_a_grading_role(app, db_session):
    from tests.conftest import create_authenticated_client
    from tests.helpers.factories import UserFactory

    uploader = UserFactory.create_optometrist(db_session, username="pwa_optometrist")
    db_session.flush()
    other = create_authenticated_client(app, uploader, db_session)

    assert other.get("/grader/").status_code == 403


def test_home_is_allowed_for_a_grader(app, db_session, ophthalmologist_user):
    from tests.conftest import create_authenticated_client

    grader = create_authenticated_client(app, ophthalmologist_user, db_session)

    assert grader.get("/grader/").status_code == 200


def test_direct_link_survives_the_login_redirect(client):
    """The global login guard must carry the requested path so a shared case
    link opens that case after sign-in instead of the web dashboard."""
    response = client.get("/grader/open/task/abc-123/resident")

    assert response.status_code == 302
    from urllib.parse import parse_qs, urlsplit

    location = urlsplit(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == ["/grader/open/task/abc-123/resident"]


def test_home_renders_queues_without_caching(app, db_session, ophthalmologist_user):
    from tests.conftest import create_authenticated_client

    response = create_authenticated_client(app, ophthalmologist_user, db_session).get("/grader/")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    page = response.get_data(as_text=True)
    assert 'data-bs-theme="dark"' in page
    assert 'rel="manifest"' in page
    assert "Your queues" in page


# --------------------------------------------------------------------------- #
# Shared workbench body
# --------------------------------------------------------------------------- #


class _Transaction:
    def __enter__(self):
        return "db"

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_workbench_route_renders_pwa_template_with_pwa_links(app, monkeypatch):
    rendered = []
    dto = SimpleNamespace(to_dict=lambda: {"lease": {"session_uuid": "session-uuid"}})
    monkeypatch.setattr(workbench_page, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(workbench_page, "transaction_scope", _Transaction)
    monkeypatch.setattr(workbench_page, "load_workbench", lambda *args, **kwargs: dto)
    monkeypatch.setattr(
        workbench_page,
        "render_template",
        lambda template, **context: rendered.append((template, context)) or "rendered",
    )

    with app.test_request_context("/grader/workbench/session-uuid"):
        flask_session["grading_workbench:session-uuid"] = {"token": "tok", "generation": 1}
        body, status, headers = unwrap(grader_pwa.workbench)("session-uuid")

    assert status == 200
    assert headers["Cache-Control"] == "no-store, private"
    template, context = rendered[0]
    assert template == "grader_pwa/workbench.html"
    assert context["session_token"] == "tok"
    assert context["workbench_dashboard_url"] == "/grader/"
    assert context["workbench_url_template"] == "/grader/workbench/{uuid}"


def test_web_workbench_route_is_unchanged(app, monkeypatch):
    rendered = []
    dto = SimpleNamespace(to_dict=lambda: {"lease": {"session_uuid": "session-uuid"}})
    monkeypatch.setattr(workbench_page, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(workbench_page, "transaction_scope", _Transaction)
    monkeypatch.setattr(workbench_page, "load_workbench", lambda *args, **kwargs: dto)
    monkeypatch.setattr(
        workbench_page,
        "render_template",
        lambda template, **context: rendered.append((template, context)) or "rendered",
    )

    with app.test_request_context("/grading/workbench/session-uuid"):
        flask_session["grading_workbench:session-uuid"] = {"token": "tok", "generation": 1}
        unwrap(workbench_page.workbench_page)("session-uuid")

    template, context = rendered[0]
    assert template == "grading/workbench.html"
    assert "workbench_dashboard_url" not in context
    assert "workbench_url_template" not in context


def test_pwa_workbench_template_reuses_the_shared_body_and_filters():
    pwa = (ROOT / "templates/grader_pwa/workbench.html").read_text()
    web = (ROOT / "templates/grading/workbench.html").read_text()
    layout = (ROOT / "templates/grader_pwa/_layout.html").read_text()
    base = (ROOT / "templates/base.html").read_text()

    assert '{% include "grading/_workbench_body.html" %}' in pwa
    assert '{% include "grading/_workbench_body.html" %}' in web
    assert '{% include "_viewer_filter_defs.html" %}' in layout
    assert '{% include "_viewer_filter_defs.html" %}' in base


def test_session_controller_reads_config_and_flushes_drafts_on_hide():
    controller = (ROOT / "static/js/grading-workbench-session.js").read_text()
    body = (ROOT / "templates/grading/_workbench_body.html").read_text()

    assert "data-workbench-config" in body
    assert "'workbenchUrlTemplate': workbench_url_template|default(none)" in body
    assert "config.workbenchUrlTemplate.replace('{uuid}'" in controller
    assert "document.addEventListener('visibilitychange'" in controller
    assert "flushDraft().catch" in controller


def test_touch_pan_lock_is_one_finger_only():
    viewer = (ROOT / "static/js/grading-viewer.js").read_text()
    editor = (ROOT / "static/js/feature-geometry-editor.js").read_text()

    assert "if (isPanLocked() && e.touches.length === 1)" in viewer
    assert "root.dataset.imggrMultiTouch = e.touches.length >= 2 ? 'true' : 'false'" in viewer
    assert "function isSecondaryTouch(event)" in editor
    assert 'state.viewerRoot?.dataset?.imggrMultiTouch === "true"' in editor


def test_pwa_and_web_workbench_templates_render_the_same_body(app, db_session, ophthalmologist_user):
    """Render both hosts with one real WorkbenchDTO: no undefined context, the
    same panel hooks, and only the host-specific links differ."""
    from datetime import timedelta

    from flask import render_template
    from flask_login import login_user

    from auth.utils import utcnow
    from grading.workbench.contracts import (
        WorkbenchAnnotationDTO,
        WorkbenchDTO,
        WorkbenchGradeOptionDTO,
        WorkbenchLeaseDTO,
        WorkbenchMediaDTO,
        WorkbenchPanelDTO,
        WorkbenchSourceDTO,
    )

    now = utcnow()
    panel = WorkbenchPanelDTO(
        task_uuid="task-1",
        disease_id=1,
        disease_name="Glaucoma",
        target_level="image",
        scope_id=None,
        image_position=1,
        editable=True,
        unavailable_reason=None,
        media=WorkbenchMediaDTO(
            source_type="encounter_file", image_uuid="img-1", media_url="/media/img-1", laterality="OD"
        ),
        evidence=(),
        grades=(WorkbenchGradeOptionDTO(id=1, impression="Normal", guidelines=None),),
        annotation=WorkbenchAnnotationDTO(
            enabled=False, policy_source="default", project_id=None, policy_revision=1,
            enabled_tools=(), default_feature_policy={}, project_classes=(),
        ),
        existing_grade=None,
        consensus=None,
        draft_observation=None,
        task_state="pending",
        fields={"label": "label_task-1", "comment": "comment_task-1", "geometry": "geometry_task-1",
                "annotation_policy_revision": "annotation_policy_revision_task-1"},
    )
    workbench = WorkbenchDTO(
        lease=WorkbenchLeaseDTO(
            session_uuid="session-1", role_slot="resident", workflow="single", token_generation=1,
            acquired_at=now, idle_expires_at=now + timedelta(minutes=10),
            absolute_expires_at=now + timedelta(minutes=30),
        ),
        configuration_fingerprint="fp",
        source=WorkbenchSourceDTO(source_type="encounter_file", profile_id=None, profile_lineage="legacy",
                                  project_id=None, lab_unit_id=1),
        panels=(panel,),
        allowed_actions=("save_close", "save_next"),
    ).to_dict()

    with app.test_request_context("/grader/workbench/session-1"):
        login_user(ophthalmologist_user)
        pwa = render_template(
            "grader_pwa/workbench.html", workbench=workbench, session_token="tok",
            submission_idempotency_key="key", workbench_dashboard_url="/grader/",
            workbench_url_template="/grader/workbench/{uuid}",
        )
        web = render_template(
            "grading/workbench.html", workbench=workbench, session_token="tok",
            submission_idempotency_key="key",
        )

    for page in (pwa, web):
        assert 'id="grading-workbench"' in page
        assert "data-workbench-config" in page
        assert 'class="imggr-filters btn-group btn-group-sm"' in page
        assert "grading-workbench-session.js" in page
        assert 'id="pswp-greenmono" color-interpolation-filters="sRGB"' in page
    assert 'data-bs-theme="dark"' in pwa
    assert "grader-pwa.css" in pwa and "grader-pwa.js" in pwa
    assert '"workbenchUrlTemplate": "/grader/workbench/{uuid}"' in pwa
    assert '"dashboardUrl": "/grader/"' in pwa
    assert '"dashboardUrl": "/grading/"' in web
    assert '"workbenchUrlTemplate": null' in web
    assert "navbar" not in pwa and "navbar" in web


# --------------------------------------------------------------------------- #
# Demo mode
# --------------------------------------------------------------------------- #


def test_demo_is_public_and_renders_a_full_encounter_set(client):
    response = client.get("/grader/demo")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    page = response.get_data(as_text=True)
    # Two disease scopes, each with four image targets and one encounter target.
    assert page.count('data-target-level="image"') == 8
    assert page.count('data-target-level="encounter"') == 2
    assert page.count('data-scope-id="1"') == 5 and page.count('data-scope-id="2"') == 5
    assert '"demo": true' in page
    assert "Demo · synthetic images · nothing is saved" in page
    assert "window.currentUserId = null;" in page
    for name in ("od-disc.png", "od-macula.png", "os-disc.png", "os-macula.png"):
        assert f"/static/grader-pwa/demo/{name}" in page
        assert (ROOT / "static/grader-pwa/demo" / name).is_file()


def test_demo_uses_configured_schemes_when_present(app, db_session, monkeypatch):
    import grader_pwa.demo as demo_module
    from models import Disease, DiseaseGrading

    image_disease = Disease(name="PWA Demo Image", grading_scope="image")
    encounter_disease = Disease(name="PWA Demo Encounter", grading_scope="encounter")
    db_session.add_all([image_disease, encounter_disease])
    db_session.flush()
    db_session.add_all([
        DiseaseGrading(disease_id=image_disease.id, impression="Configured image grade", display_order=1, is_active=True),
        DiseaseGrading(disease_id=image_disease.id, impression="Retired grade", display_order=2, is_active=False),
        DiseaseGrading(disease_id=encounter_disease.id, impression="Configured set grade", display_order=1, is_active=True),
    ])
    db_session.flush()
    monkeypatch.setattr(
        demo_module,
        "DEMO_SCOPES",
        (("PWA Demo Image", "PWA Demo Encounter"), ("Glaucoma", "Glaucoma Encounter Status")),
    )

    with app.test_request_context("/grader/demo"):
        workbench = demo_module.build_demo_workbench(db_session)

    configured = [panel for panel in workbench.panels if panel.scope_id == 1]
    assert [grade.impression for grade in configured[0].grades] == ["Configured image grade"]
    assert [grade.impression for grade in configured[-1].grades] == ["Configured set grade"]
    assert configured[0].disease_id == image_disease.id
    assert configured[-1].disease_id == encounter_disease.id
    # "Glaucoma Encounter Status" is not seeded here, so that target uses the fallback.
    glaucoma = [panel for panel in workbench.panels if panel.scope_id == 2]
    assert glaucoma[-1].grades[0].id < 0
    assert [grade.impression for grade in glaucoma[-1].grades] == ["Normal", "Glaucoma/Suspect", "Cannot Grade"]


def test_session_controller_answers_api_locally_in_demo_mode():
    controller = (ROOT / "static/js/grading-workbench-session.js").read_text()

    assert "if (config.demo) return demoApi(path, options);" in controller
    assert "next_workbench: null" in controller


def test_overlay_canvas_is_viewport_clipped_and_capped():
    """Coordinate/memory audit (2026-09-02): the annotation overlay must cover
    only the visible part of the image, carry the offset in the context
    transform, and cap its backing store - a zoomed 4K image previously
    allocated a canvas the size of the whole scaled image."""
    editor = (ROOT / "static/js/feature-geometry-editor.js").read_text()

    assert "const MAX_CANVAS_SCALE = 2;" in editor
    assert "const MAX_CANVAS_PIXELS = 4096 * 4096;" in editor
    assert "const visLeft = Math.max(m.drawRect.left, m.mainRect.left);" in editor
    assert "state.ctx.setTransform(scale, 0, 0, scale, -offsetX * scale, -offsetY * scale);" in editor
    assert "state.ctx.clearRect(0, 0, state.canvas.width, state.canvas.height);" in editor
    # Coordinate projections stay in CSS pixels, independent of devicePixelRatio.
    assert "const x = ((clientX - m.drawRect.left) / m.drawRect.width) * m.naturalWidth;" in editor


def test_encounter_targets_never_mount_into_another_sidebar():
    editor = (ROOT / "static/js/feature-geometry-editor.js").read_text()

    assert 'return panelRoot.querySelector("[data-geometry-sidebar-host]");' in editor
