from inspect import unwrap
from types import SimpleNamespace
from uuid import UUID

from flask import session as flask_session

import grading.workbench_page as workbench_page


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
