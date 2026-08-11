from inspect import unwrap
from pathlib import Path
from types import SimpleNamespace

import grading.encounter_set_package_grading as package_transport
from grading.workbench.package_workflow import ordered_package_tasks


def _task(task_id, target_level, *, position=None, laterality=None, disease_name="Disease", scope_order=0):
    image = None
    if position is not None:
        image = SimpleNamespace(
            spatial_position=position,
            metadata_json={"laterality": laterality},
        )
    return SimpleNamespace(
        id=task_id,
        grading_target_level=target_level,
        encounter_set_image=image,
        encounter_set_scope=SimpleNamespace(display_order=scope_order),
        disease=SimpleNamespace(name=disease_name),
    )


def test_package_workflow_orders_scope_images_then_encounter_targets():
    tasks = [
        _task(1, "encounter", disease_name="Person Wise"),
        _task(2, "image", position=1, laterality="OS", disease_name="RT"),
        _task(3, "image", position=1, laterality="OD", disease_name="LT"),
        _task(4, "image", position=2, laterality="OD", disease_name="RT"),
        _task(5, "image", position=1, laterality="OD", disease_name="Linked", scope_order=1),
    ]

    ordered = ordered_package_tasks(tasks)

    assert [task.id for task in ordered] == [3, 4, 2, 1, 5]


def test_shared_jinja_workbench_uses_dto_and_task_qualified_submission():
    template = (
        Path(package_transport.__file__).parents[1]
        / "templates/grading/workbench.html"
    ).read_text()

    assert "workbench.panels" in template
    assert "panel.fields.label" in template
    assert "data-grade-option" in template
    assert "sanitizeGuidelineHtml" in template
    assert "guidelines.innerHTML = sanitizeGuidelineHtml" in template
    assert "const allowedTags = new Set(['UL', 'OL', 'LI', 'P', 'BR', 'STRONG', 'EM', 'B', 'I'])" in template
    assert "removeAttribute(attribute.name)" in template
    assert 'class="col-6"' in template
    assert "panel.fields.geometry" in template
    assert "data-geometry-sidebar-host" in template
    assert 'data-grading-form="true"' in template
    assert "data-features-section" in template
    assert "data-features-container" in template
    assert "gwb-shell is-expanded" in template
    assert "data-workbench-expand" in template
    assert "Image {{ image_nav.index }} of" in template
    assert "set_context.enabled" in template
    assert "{% if workbench.panels|length > 1 %}" in template
    assert "data-image-navigate=\"prev\"" in template
    assert "data-image-navigate=\"next\"" in template
    assert "data-encounter-navigate" in template
    assert "Grade set" in template
    assert "{{ 'Image' if panel.target_level == 'image' else 'Set' }}:" in template
    assert '<legend class="visually-hidden">Select grade</legend>' in template
    assert template.index('text-uppercase fw-semibold mb-1">Grade') < template.index("{{ 'Image' if panel.target_level == 'image' else 'Set' }}:")
    assert template.index("{{ 'Image' if panel.target_level == 'image' else 'Set' }}:") < template.index('data-image-navigate="prev"')
    assert "carousel?.to(panels.indexOf(encounterPanel))" in template
    assert "document.addEventListener('DOMContentLoaded', initializeCarousel" in template
    assert "carousel = window.bootstrap.Carousel.getOrCreateInstance" in template
    assert "data-workbench-progress" in template
    assert "data-workbench-pager" in template
    assert "data-workbench-submit-actions" in template
    assert "submitActionGroups" in template
    assert "group.closest('[data-task-uuid]') !== activePanel" in template
    assert "contextualSubmission" in template
    assert "allImagesGraded" in template
    assert "activePanel === encounterPanel" in template
    assert "data-encounter-image-grade" in template
    assert "No image targets" in template
    assert 'data-workbench-navigate="prev"' in template
    assert 'data-workbench-navigate="next"' in template
    assert "This target intentionally has no primary image" not in template
    assert "imggr-zoom-slider" in template
    assert "gwb-toolbar-left" in template
    assert "gwb-toolbar-right" in template
    assert "flex-basis: 100%" in template
    assert "gwb-adjustment-control" in template
    assert ".gwb-adjustment-control .imggr-bright" in template
    assert "width: 100%; min-width: 0; max-width: none" in template
    assert "flex-wrap: nowrap" in template
    assert "overflow-x: auto" in template
    assert "fa-circle-info" in template
    assert "imggr-bright" in template
    assert "imggr-contrast" in template
    assert "imggr-loupe-toggle" in template
    assert "data-clear-selection" in template
    assert "data.existingSelectedFeatures = []" in template
    assert "panel.querySelector('[data-feature-geometry-field]').value = ''" in template
    assert "feature-geometry-editor.js" in template
    assert "/api/grading/workbench/sessions/${sessionUuid}/submit" in template
    assert "spinner-border spinner-border-sm" in template
    assert "data-workbench-submit-overlay" in template
    assert "gwb-loader-logo" in template
    assert "retina_svg_logo.svg" in template
    assert "gwb-loader-counter-spin" in template
    assert "rotate(-360deg)" in template
    assert "Saving grades and loading the next case" in template
    assert "submitOverlay.classList.remove('d-none')" in template
    assert "submitOverlay.classList.add('d-none')" in template
    assert "Saving grades" in template
    assert "Grades saved. Opening the next case" in template
    assert "clearInterval(heartbeatTimer)" in template
    assert "result.next_workbench.workbench_url" in template


def test_shared_jinja_workbench_compiles(app):
    assert app.jinja_env.get_template("grading/workbench.html") is not None


def test_geometry_editor_uses_annotations_heading():
    editor = (
        Path(package_transport.__file__).parents[1]
        / "static/js/feature-geometry-editor.js"
    ).read_text()

    assert '<span class="fw-semibold">Annotations</span>' in editor
    assert '>Current Disease</span>' not in editor
    assert 'gradingFeatureGroup.label = "Selected grading features"' in editor
    assert 'projectClassGroup.label = "Project classes"' in editor
    assert 'option.dataset.classSource = featureId < 0 ? "project_class" : "grading_feature"' in editor
    assert '>Annotation class</span>' in editor
    assert 'data-fgx-tool-category="bounding-box"' in editor
    assert 'data-fgx-tool-category="segmentation"' in editor
    assert '>Rectangle</span>' in editor
    assert 'not a bounding box' in editor
    assert 'data-fgx-add-freeform' in editor
    assert '>Freeform</span>' in editor
    assert '["[data-fgx-add-freeform]", "polygon"]' in editor
    assert '(mode === MODES.POLYGON && state.pendingCreateType === "polygon")' in editor
    assert 'if (state.pendingCreateType === "polygon")' in editor


def test_cached_package_form_delegates_to_workbench_transport(app, monkeypatch):
    calls = []

    class Transaction:
        def __enter__(self):
            return "db"

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(package_transport, "transaction_scope", lambda: Transaction())
    monkeypatch.setattr(package_transport, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(
        package_transport,
        "submit_package_form",
        lambda db, user_id, form: calls.append((db, user_id, form["package_uuid"])),
    )

    with app.test_request_context(
        "/grading/encounter_set_package/submit",
        method="POST",
        data={"package_uuid": "package-uuid", "slot": "resident"},
    ):
        response = unwrap(unwrap(package_transport.encounter_set_package_submit))()

    assert response.status_code == 302
    assert calls == [("db", 7, "package-uuid")]
