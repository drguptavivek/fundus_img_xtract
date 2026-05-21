from __future__ import annotations

from contextlib import contextmanager
from inspect import unwrap

import admin.remidio as remidio_admin
from flask import Flask


@contextmanager
def _fake_transaction_scope():
    yield object()


def test_stuck_remidio_uploads_status_returns_dry_run_payload(monkeypatch):
    calls = []

    def fake_cleanup(db, *, date_folder=None, dry_run=True, limit=500):
        calls.append({"date_folder": date_folder, "dry_run": dry_run, "limit": limit})
        return {
            "dry_run": dry_run,
            "date_folder": date_folder,
            "scanned": 98,
            "eligible": 98,
            "moved": 0,
            "skipped": 0,
            "errors": 0,
            "items": [],
        }

    monkeypatch.setattr(remidio_admin, "transaction_scope", _fake_transaction_scope)
    monkeypatch.setattr(remidio_admin, "cleanup_processed_zip_intake_files", fake_cleanup)

    app = Flask(__name__)
    with app.test_request_context(
        "/admin/stuck-remidio-uploads/status?date_folder=2026_04_20&limit=200"
    ):
        response = unwrap(remidio_admin.stuck_remidio_uploads_status)()

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["eligible"] == 98
    assert calls == [{"date_folder": "2026_04_20", "dry_run": True, "limit": 200}]


def test_stuck_remidio_uploads_cleanup_executes_guarded_cleanup(monkeypatch):
    calls = []

    def fake_cleanup(db, *, date_folder=None, dry_run=True, limit=500):
        calls.append({"date_folder": date_folder, "dry_run": dry_run, "limit": limit})
        return {
            "dry_run": dry_run,
            "date_folder": date_folder,
            "scanned": 98,
            "eligible": 98,
            "moved": 98,
            "skipped": 0,
            "errors": 0,
            "items": [],
        }

    monkeypatch.setattr(remidio_admin, "transaction_scope", _fake_transaction_scope)
    monkeypatch.setattr(remidio_admin, "cleanup_processed_zip_intake_files", fake_cleanup)

    app = Flask(__name__)
    with app.test_request_context(
        "/admin/stuck-remidio-uploads/cleanup",
        method="POST",
        json={"date_folder": "2026_04_20", "dry_run": False, "limit": 200},
    ):
        response = unwrap(remidio_admin.cleanup_stuck_remidio_uploads)()

    response, status_code = response
    assert status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["moved"] == 98
    assert calls == [{"date_folder": "2026_04_20", "dry_run": False, "limit": 200}]
