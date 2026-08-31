"""Regression tests for import-light modules used by Celery workers."""

from __future__ import annotations

import subprocess
import sys


def test_worker_services_do_not_import_page_routes() -> None:
    script = """
import sys

import review.discrepancy_export
import tasks.lineage

unexpected = {
    name
    for name in sys.modules
    if name.startswith("review.route_") or name.startswith("tasks.route_")
}
assert not unexpected, sorted(unexpected)
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_flask_app_explicitly_registers_deferred_routes(app) -> None:
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/review/discrepancy-review" in rules
    assert any(rule.startswith("/tasks/") for rule in rules)
