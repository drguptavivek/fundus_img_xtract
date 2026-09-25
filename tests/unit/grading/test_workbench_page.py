from inspect import unwrap
from types import SimpleNamespace
from uuid import UUID

from flask import get_flashed_messages, session as flask_session

import grading.workbench_page as workbench_page
from grading.workbench.errors import ActiveSessionExists


class _Transaction:
    def __enter__(self):
        return "db"

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_workbench_get_issues_one_new_submission_key_per_render(app, monkeypatch):
    rendered = []
    dto = SimpleNamespace(to_dict=lambda: {"lease": {"session_uuid": "session-uuid"}})
    monkeypatch.setattr(workbench_page, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(workbench_page, "transaction_scope", _Transaction)
    monkeypatch.setattr(workbench_page, "load_workbench", lambda *args, **kwargs: dto)
    monkeypatch.setattr(
        workbench_page,
        "render_template",
        lambda template, **context: rendered.append((template, context)) or "rendered",
    )

    def render_once():
        with app.test_request_context("/grading/workbench/session-uuid"):
            flask_session["grading_workbench:session-uuid"] = {
                "token": "private-token",
                "generation": 1,
            }
            return unwrap(workbench_page.workbench_page)("session-uuid")

    first = render_once()
    second = render_once()

    assert first[0] == "rendered"
    assert second[0] == "rendered"
    assert [item[0] for item in rendered] == [
        "grading/workbench.html",
        "grading/workbench.html",
    ]
    first_key = rendered[0][1]["submission_idempotency_key"]
    second_key = rendered[1][1]["submission_idempotency_key"]
    assert UUID(first_key).version == 4
    assert UUID(second_key).version == 4
    assert first_key != second_key


def test_start_grading_warns_when_restoring_an_existing_session(app, monkeypatch):
    lease = SimpleNamespace(session_uuid="older-session", token_generation=3)
    dto = SimpleNamespace(lease=lease)
    monkeypatch.setattr(workbench_page, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(workbench_page, "transaction_scope", _Transaction)
    monkeypatch.setattr(
        workbench_page,
        "resume_workbench",
        lambda *args, **kwargs: (dto, "rotated-token"),
    )
    monkeypatch.setattr(workbench_page, "remember_session_token", lambda *args: None)
    monkeypatch.setattr(workbench_page, "url_for", lambda endpoint, **values: "/restored")

    def acquire(_db):
        raise ActiveSessionExists(
            "Active session exists.", details={"session_uuid": "older-session"}
        )

    with app.test_request_context("/grading/grade/1/resident"):
        response = workbench_page._open_workbench(
            acquire,
            workbench_endpoint="grading.workbench_page",
            fallback_endpoint="grading.index",
        )
        assert response.location == "/restored"
        assert get_flashed_messages(with_categories=True) == [
            ("warning", workbench_page.RESTORED_SESSION_NOTICE)
        ]
