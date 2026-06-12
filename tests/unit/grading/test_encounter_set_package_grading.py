from types import SimpleNamespace

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
