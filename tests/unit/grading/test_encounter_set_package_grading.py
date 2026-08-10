from inspect import unwrap
import json
from pathlib import Path
from types import SimpleNamespace

import grading.encounter_set_package_grading as package_grading
from grading.grade_feature_submission import prepare_grade_feature_submission
from markupsafe import Markup
from grading.encounter_set_package_grading import _ordered_package_tasks


def _task(task_id, target_level, *, position=None, laterality=None, disease_name="Disease", state="pending"):
    image = None
    if position is not None:
        image = SimpleNamespace(spatial_position=position, metadata_json={"laterality": laterality})
    return SimpleNamespace(
        id=task_id,
        grading_target_level=target_level,
        encounter_set_image=image,
        disease=SimpleNamespace(name=disease_name),
        state=state,
        grades=[],
    )


def _label_query(labels):
    class LabelQuery:
        def options(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return labels

    return LabelQuery()


def test_ordered_package_tasks_groups_images_by_laterality_before_encounter_target():
    package = SimpleNamespace(
        tasks=[
            _task(1, "encounter", disease_name="Person Wise"),
            _task(2, "image", position=1, laterality="OS", disease_name="RT"),
            _task(3, "image", position=1, laterality="OD", disease_name="LT"),
            _task(4, "image", position=2, laterality="OD", disease_name="RT"),
        ]
    )

    ordered = _ordered_package_tasks(package)

    assert [(task.grading_target_level, task.id) for task in ordered] == [
        ("image", 3),
        ("image", 4),
        ("image", 2),
        ("encounter", 1),
    ]


def test_linked_package_completes_root_scope_before_linked_scope():
    root_image = _task(1, "image", position=1, disease_name="DR")
    root_set = _task(2, "encounter", disease_name="DR Set")
    linked_image = _task(3, "image", position=1, disease_name="DME")
    linked_set = _task(4, "encounter", disease_name="DME Set")
    root_scope = SimpleNamespace(display_order=0)
    linked_scope = SimpleNamespace(display_order=1)
    root_image.encounter_set_scope = root_scope
    root_set.encounter_set_scope = root_scope
    linked_image.encounter_set_scope = linked_scope
    linked_set.encounter_set_scope = linked_scope

    ordered = package_grading._ordered_tasks([
        linked_image,
        root_set,
        linked_set,
        root_image,
    ])

    assert [task.id for task in ordered] == [1, 2, 3, 4]


def test_task_panel_is_locked_when_target_is_not_allocated(monkeypatch):
    task = _task(9, "image")
    task.uuid = "task-uuid"
    task.disease_id = 11
    db = SimpleNamespace(query=lambda model: _label_query([]))
    monkeypatch.setattr(package_grading, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(
        package_grading,
        "get_user_eligibility_for_task",
        lambda session, user_id, task_id, slot: False,
    )

    panel = package_grading._task_panel(db, task, "resident")

    assert panel["available"] is False
    assert panel["unavailable_reason"] == "Not allocated to you"


def test_task_panel_sanitizes_guideline_rich_text_for_rendering(monkeypatch):
    task = _task(10, "image")
    task.uuid = "task-uuid"
    task.disease_id = 11
    label = SimpleNamespace(
        id=3,
        guidelines="<p><strong>Hard Signs</strong></p><script>alert(1)</script>",
        features=[],
        impression="Glaucoma",
        display_order=1,
        is_ungradable=False,
    )
    db = SimpleNamespace(query=lambda model: _label_query([label]))
    monkeypatch.setattr(package_grading, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(
        package_grading,
        "get_user_eligibility_for_task",
        lambda session, user_id, task_id, slot: True,
    )

    panel = package_grading._task_panel(db, task, "resident")

    guideline_html = panel["guideline_html_by_label_id"][label.id]
    assert isinstance(guideline_html, Markup)
    assert guideline_html == "<p><strong>Hard Signs</strong></p>alert(1)"


def test_grade_feature_submission_serializes_selected_features_in_display_order():
    features = [
        SimpleNamespace(id=7, label="RNFL loss", sr_no=2),
        SimpleNamespace(id=6, label="Disc hemorrhage", sr_no=1),
    ]
    db = SimpleNamespace(query=lambda model: _label_query(features))
    task = SimpleNamespace(encounter_set_image=None)

    result = prepare_grade_feature_submission(
        db,
        task=task,
        label_id=3,
        raw_selected_features=["7", "6", "7"],
        raw_feature_geometry=None,
        existing_grade=None,
    )

    assert json.loads(result.selected_features_json) == [
        {"id": 6, "label": "Disc hemorrhage", "sr_no": 1},
        {"id": 7, "label": "RNFL loss", "sr_no": 2},
    ]
    assert result.feature_geometry_json is None


def test_workbench_template_wires_features_and_per_image_annotation_contexts():
    template = (
        Path(package_grading.__file__).parents[1]
        / "templates/grading/_fullscreen_grading_workbench.html"
    ).read_text()

    assert 'data-features-section' in template
    assert "checkbox.name = 'selected_features_' + panel.dataset.taskUuid" in template
    assert 'data-feature-geometry-field="{{ task.uuid }}"' in template
    assert 'data-geometry-sidebar-host' in template
    assert "feature-geometry-editor.js" in template


def test_package_submit_delegates_atomic_package_dto_to_record_service(app, monkeypatch):
    task = _task(42, "encounter")
    task.uuid = "task-uuid"
    task.disease_id = 11
    package = SimpleNamespace(
        uuid="package-uuid",
        name="Package",
        tasks=[task],
        state="pending",
        revision_number=3,
        resident_user_id=None,
    )
    db = SimpleNamespace(
        added=[],
        add=lambda grade: db.added.append(grade),
        flush=lambda: None,
        query=lambda model: SimpleNamespace(
            filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: None)
        ),
    )
    calls = []

    class Transaction:
        def __enter__(self):
            return db

        def __exit__(self, exc_type, exc, tb):
            return False

    class LabelQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=5)

    class GradeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    def query(model):
        if model is package_grading.DiseaseGrading:
            return LabelQuery()
        return GradeQuery()

    db.query = query
    monkeypatch.setattr(package_grading, "transaction_scope", lambda: Transaction())
    monkeypatch.setattr(package_grading, "_fetch_package", lambda session, uuid, for_update=False: package)
    monkeypatch.setattr(package_grading, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(package_grading, "get_user_eligibility_for_task", lambda session, user_id, task_id, slot: True)
    monkeypatch.setattr(package_grading, "editable_tasks", lambda package, slot, user_id: [task])
    monkeypatch.setattr(package_grading, "_package_slot_eligible", lambda *args: True)
    monkeypatch.setattr(package_grading, "cleanup_task_tracker", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        package_grading,
        "submit_package",
        lambda session, submitted_package, dto: calls.append((session, submitted_package, dto)),
    )

    with app.test_request_context(
        "/encounter_set_package/submit",
        method="POST",
        data={
            "package_uuid": package.uuid,
            "slot": "resident",
            "package_revision": "3",
            f"label_id_{task.uuid}": "5",
        },
    ):
        response = unwrap(package_grading.encounter_set_package_submit)()

    assert response.status_code == 302
    assert len(calls) == 1
    assert calls[0][0] is db
    assert calls[0][1] is package
    assert calls[0][2].expected_package_revision == 3
    assert calls[0][2].targets[0].task_uuid == task.uuid
