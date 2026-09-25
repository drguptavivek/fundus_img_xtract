"""Regression tests for import-light modules used by Celery workers."""

from __future__ import annotations

import subprocess
import sys
from inspect import signature

from celery_tasks.tasks.export_tasks import run_project_export_task


def test_worker_services_do_not_import_page_routes() -> None:
    script = """
import sys

import review.discrepancy_export
import project_review.export_service
import tasks.lineage

unexpected = {
    name
    for name in sys.modules
    if (
        name.startswith("review.route_")
        or name.startswith("tasks.route_")
        or name == "datasets.routes"
    )
}
assert not unexpected, sorted(unexpected)
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_flask_app_explicitly_registers_deferred_routes(app) -> None:
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/review/discrepancy-review" in rules
    assert "/datasets/list" in rules
    assert any(rule.startswith("/tasks/") for rule in rules)


def test_project_export_task_accepts_standard_enqueue_context() -> None:
    parameters = signature(run_project_export_task.run).parameters

    assert "user_id" in parameters
    assert "hospital_id" in parameters
