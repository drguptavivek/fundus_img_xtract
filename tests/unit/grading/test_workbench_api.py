from inspect import unwrap
from types import SimpleNamespace

import api.grading_workbench as workbench_api


class _Transaction:
    def __enter__(self):
        return "db"

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_save_next_returns_direct_workbench_url_and_remembers_browser_token(
    app,
    monkeypatch,
):
    lease = SimpleNamespace(
        session_uuid="next-session-uuid",
        token_generation=2,
    )
    next_workbench = SimpleNamespace(
        lease=lease,
        to_dict=lambda: {
            "lease": {"session_uuid": lease.session_uuid, "token_generation": 2},
            "panels": [{"task_uuid": "next-task-uuid"}],
        },
    )
    remembered = []
    monkeypatch.setattr(workbench_api, "current_user", SimpleNamespace(id=7))
    monkeypatch.setattr(workbench_api, "transaction_scope", _Transaction)
    monkeypatch.setattr(
        workbench_api,
        "submit_workbench",
        lambda *args, **kwargs: {
            "event_uuid": "event-uuid",
            "idempotent_replay": False,
            "queue_request": {
                "disease_id": 1,
                "requested_slot": "resident",
                "lab_unit_id": 3,
            },
        },
    )
    monkeypatch.setattr(
        workbench_api,
        "acquire_next_workbench",
        lambda *args, **kwargs: (next_workbench, "next-private-token"),
    )
    monkeypatch.setattr(
        workbench_api,
        "remember_session_token",
        lambda *args: remembered.append(args),
    )

    with app.test_request_context(
        "/api/grading/workbench/sessions/current-session/submit",
        method="POST",
        json={"action": "save_next"},
    ):
        response = unwrap(workbench_api.submit_workbench_session)("current-session")

    payload = response.get_json()
    assert payload["success"] is True
    assert payload["next_workbench"]["workbench_url"] == (
        "/grading/workbench/next-session-uuid"
    )
    assert remembered == [("next-session-uuid", "next-private-token", 2)]
