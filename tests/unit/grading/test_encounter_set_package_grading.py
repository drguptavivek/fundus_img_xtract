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
    assert "panel.fields.geometry" in template
    assert "data-geometry-sidebar-host" in template
    assert "feature-geometry-editor.js" in template
    assert "/api/grading/workbench/sessions/${sessionUuid}/submit" in template


def test_shared_jinja_workbench_compiles(app):
    assert app.jinja_env.get_template("grading/workbench.html") is not None


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
