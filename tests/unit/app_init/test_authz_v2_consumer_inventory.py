import json
import subprocess
import sys

from app import create_app
from celery_app import celery_app
from celery_tasks.tasks import _import_all
from scripts.authz_v2_inventory import (
    build_live_consumer_inventory,
)


def test_live_http_and_celery_inventory_matches_reviewed_baseline():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.authz_v2_inventory"],
        check=True,
        capture_output=True,
        text=True,
    )
    inventory = json.loads(result.stdout)
    assert inventory["counts"] == {
        "legacy_action_literal": 50,
        "legacy_unmapped": 630,
        "automation_unmapped": 47,
        "query_candidate_unmapped": 977,
    }
    assert (
        inventory["identity_fingerprint"]
        == "02955f29a2d0bfb40ca38be17d8308cb34c5cbe8ed39d0fa3929a4538114d85d"
    )


def test_every_inventory_row_has_a_traceable_runtime_identity():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    assert all(row.name and row.source and row.line for row in rows)
    identities = [(row.kind, row.name, row.methods, row.path) for row in rows]
    assert len(identities) == len(set(identities))
