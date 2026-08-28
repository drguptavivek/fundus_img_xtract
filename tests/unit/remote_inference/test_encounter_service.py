from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from remote_inference import encounter_service


class _Result:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def all(self):
        return self.value

    def scalar_one(self):
        return self.value


class _Encounter:
    def __init__(self, encounter_id: int, uuid: str):
        self._id = encounter_id
        self._uuid = uuid
        self._lab_unit_id = 7
        self.detached = False

    def _value(self, value):
        if self.detached:
            raise RuntimeError("detached encounter attribute accessed")
        return value

    id = property(lambda self: self._value(self._id))
    uuid = property(lambda self: self._value(self._uuid))
    lab_unit_id = property(lambda self: self._value(self._lab_unit_id))


def test_manual_job_uses_scalar_encounter_snapshot_after_session_closes(monkeypatch):
    encounter = _Encounter(42, "encounter-uuid")
    item = SimpleNamespace(source_type=None, source_id=None, source_uuid=None, task_id="stale")
    job = SimpleNamespace(items=[item])
    sessions = [SimpleNamespace(execute=lambda _query: _Result([encounter])), SimpleNamespace(execute=lambda _query: _Result(job))]

    @contextmanager
    def transaction_scope():
        session = sessions.pop(0)
        yield session
        if not sessions:
            encounter.detached = True

    monkeypatch.setattr(encounter_service, "transaction_scope", transaction_scope)
    monkeypatch.setattr(
        encounter_service,
        "list_candidates",
        lambda *_args, **_kwargs: SimpleNamespace(rows=({"encounter_id": 42, "eligible": True},)),
    )
    monkeypatch.setattr(encounter_service, "db_create_job", lambda *_args, **_kwargs: "job-token")
    queued = []
    monkeypatch.setattr(encounter_service, "enqueue_task", lambda *args, **kwargs: queued.append((args, kwargs)))
    monkeypatch.setattr("authz.project_access.can_run_wai", lambda *args, **kwargs: True)

    result = encounter_service.create_manual_job(
        encounter_ids=[42],
        project_id=3,
        user=SimpleNamespace(id=9, username="manager"),
        remote_addr="127.0.0.1",
    )

    assert result.success is True
    assert item.source_type == "patient_encounter"
    assert item.source_id == 42
    assert item.source_uuid == "encounter-uuid"
    assert item.task_id is None
    assert queued[0][0][1:] == ("job-token", [42])
