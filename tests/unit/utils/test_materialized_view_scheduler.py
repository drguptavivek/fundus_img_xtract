from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from utils import materialized_view_scheduler


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _FakeResult:
    def __init__(self, scalar_value=None, scalar_values=None):
        self._scalar_value = scalar_value
        self._scalar_values = scalar_values

    def scalar(self):
        return self._scalar_value

    def scalars(self):
        return _FakeScalarResult(self._scalar_values or [])


def test_refresh_materialized_view_uses_isolated_transactions(monkeypatch):
    executed_sql = []
    scope_entries = []
    next_log_id = 41
    per_disease_views = [
        "mvw_image_listing_glaucoma_1_v2",
        "mvw_image_listing_dr_2_v2",
    ]

    class _FakeDb:
        def execute(self, statement, params=None):
            sql = str(statement)
            executed_sql.append((sql, params))
            if "RETURNING id" in sql:
                return _FakeResult(scalar_value=next_log_id)
            if "SELECT matviewname" in sql:
                return _FakeResult(scalar_values=per_disease_views)
            return _FakeResult()

    @contextmanager
    def fake_transaction_scope():
        scope_entries.append("enter")
        yield _FakeDb()

    class _FakeAppContext:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    app = SimpleNamespace(
        config={
            "MATERIALIZED_VIEW_TIMEZONE": "Asia/Kolkata",
            "DEFAULT_DISPLAY_TIMEZONE": "Asia/Kolkata",
        },
        app_context=lambda: _FakeAppContext(),
    )

    monkeypatch.setattr(materialized_view_scheduler, "transaction_scope", fake_transaction_scope, raising=False)

    assert materialized_view_scheduler.refresh_materialized_view(app, "manual") is True

    refresh_sql = [sql for sql, _params in executed_sql if sql.startswith("REFRESH MATERIALIZED VIEW")]
    assert refresh_sql == [
        "REFRESH MATERIALIZED VIEW mvw_grading_data_all",
        "REFRESH MATERIALIZED VIEW mvw_diabetic_retinopathy_grading_pivot",
        "REFRESH MATERIALIZED VIEW mvw_glaucoma_grading_pivot",
        "REFRESH MATERIALIZED VIEW mvw_amd_grading_pivot",
        "REFRESH MATERIALIZED VIEW mvw_encounter_pivot",
        "REFRESH MATERIALIZED VIEW mvw_image_listing_all",
        "REFRESH MATERIALIZED VIEW mvw_image_listing_glaucoma_1_v2",
        "REFRESH MATERIALIZED VIEW mvw_image_listing_dr_2_v2",
    ]
    assert len(scope_entries) == 11
