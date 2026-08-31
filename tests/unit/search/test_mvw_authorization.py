"""Authorization predicates for the materialized-view image search."""

from utils.mvw_all_img_search import MVImageFilters, build_where_clause


class _DbWithoutDiseases:
    def get(self, _model, _identifier):
        return None


def test_mvw_search_requires_exact_authorized_task_ids():
    filters = MVImageFilters(
        disease_id=7,
        allowed_lab_units=[11],
        authorized_task_ids=[101, 202],
    )

    where_sql, params = build_where_clause(_DbWithoutDiseases(), filters)

    assert "gt.id = ANY(:authorized_task_ids)" in where_sql
    assert params["authorized_task_ids"] == [101, 202]
    assert "gt.lab_unit_id = ANY(:allowed_lab_units)" in where_sql


def test_mvw_search_without_authorized_tasks_is_fail_closed():
    filters = MVImageFilters(disease_id=7, allowed_lab_units=[11])

    _where_sql, params = build_where_clause(_DbWithoutDiseases(), filters)

    assert params["authorized_task_ids"] == []
