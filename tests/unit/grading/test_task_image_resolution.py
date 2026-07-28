from types import SimpleNamespace

from grading.dual_grading import _missing_task_image_reference, _resolve_task_image_uuid


def test_resolve_task_image_uuid_uses_encounter_set_image():
    task = SimpleNamespace(
        encounter_file=None,
        direct_image=None,
        encounter_set_image=SimpleNamespace(uuid="encounter-set-image-uuid"),
    )

    assert _resolve_task_image_uuid(task) == "encounter-set-image-uuid"


def test_missing_task_image_reference_reports_encounter_set_image_id():
    task = SimpleNamespace(
        encounter_file_id=None,
        direct_image_upload_id=None,
        encounter_set_image_id=42,
        patient_encounter_id=None,
    )

    assert _missing_task_image_reference(task) == "EncounterSet image ID 42"
