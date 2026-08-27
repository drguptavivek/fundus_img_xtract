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
        "authz_v2": 17,
        "legacy_action_literal": 50,
        "legacy_unmapped": 613,
        "automation_unmapped": 47,
        "query_candidate_unmapped": 977,
    }
    assert (
        inventory["identity_fingerprint"]
        == "6851094b619dd3800bdc2421d681f0b9dc97cc2c5d83ce11a047f8125680aba3"
    )


def test_high_risk_media_slice_has_no_unmapped_route():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    media_rows = [
        row for row in rows if row.kind == "http" and row.source == "media/routes.py"
    ]
    assert len(media_rows) == 17
    assert {row.classification for row in media_rows} == {"authz_v2"}
    assert all(row.canonical_actions for row in media_rows)


def test_every_inventory_row_has_a_traceable_runtime_identity():
    _import_all()
    app = create_app()
    rows = build_live_consumer_inventory(app, celery_app)
    assert all(row.name and row.source and row.line for row in rows)
    identities = [(row.kind, row.name, row.methods, row.path) for row in rows]
    assert len(identities) == len(set(identities))
