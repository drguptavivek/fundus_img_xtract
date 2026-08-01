from public.analytics import (
    _ANALYTICS_IMAGE_SOURCE_CTE,
    _IMAGE_TASK_PREDICATE,
)


def test_public_analytics_image_source_includes_encounter_set_images():
    assert "FROM encounter_set_images esi" in _ANALYTICS_IMAGE_SOURCE_CTE
    assert "'EncounterSet'::text AS upload_type" in _ANALYTICS_IMAGE_SOURCE_CTE
    assert "esi.created_at AS upload_date_utc" in _ANALYTICS_IMAGE_SOURCE_CTE


def test_public_analytics_image_task_scope_includes_only_image_backed_tasks():
    assert "gt.encounter_set_image_id IS NOT NULL" in _IMAGE_TASK_PREDICATE
    assert "gt.patient_encounter_id" not in _IMAGE_TASK_PREDICATE
