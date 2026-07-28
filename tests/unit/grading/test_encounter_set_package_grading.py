from inspect import unwrap
from types import SimpleNamespace

import grading.encounter_set_package_grading as package_grading
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


def test_package_submit_updates_task_state_with_task_id_and_db(app, monkeypatch):
    task = _task(42, "encounter")
    task.uuid = "task-uuid"
    task.disease_id = 11
    package = SimpleNamespace(uuid="package-uuid", name="Package", tasks=[task], state="pending")
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
    monkeypatch.setattr(package_grading, "has_user_graded_task", lambda session, user_id, task_id, slots: False)
    monkeypatch.setattr(package_grading, "cleanup_task_tracker", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        package_grading,
        "update_task_state_based_on_grades",
        lambda task_id, session: calls.append((task_id, session)),
    )

    with app.test_request_context(
        "/encounter_set_package/submit",
        method="POST",
        data={
            "package_uuid": package.uuid,
            "slot": "resident",
            f"label_id_{task.uuid}": "5",
        },
    ):
        response = unwrap(package_grading.encounter_set_package_submit)()

    assert response.status_code == 302
    assert calls == [(task.id, db)]
