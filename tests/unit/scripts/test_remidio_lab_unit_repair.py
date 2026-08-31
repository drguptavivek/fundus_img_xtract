from types import SimpleNamespace

import pytest

from scripts.remidio_lab_unit_repair import (
    RemidioLabUnitRepairError,
    RepairScope,
    _LabRecord,
    _validate_lab_lineage,
    apply_repair,
    preview_repair,
)


def _scope(entities, *, source=3, target=1):
    return RepairScope(
        project_id=42,
        project_code="ICMR-VG",
        binding_id=14,
        project_upload_profile_id=8,
        source_lab_unit_id=source,
        target_lab_unit_id=target,
        link_ids=(101,),
        records=[
            _LabRecord(table, row.id, row, row.lab_unit_id)
            for table, row in entities
        ],
    )


def test_preview_is_read_only(monkeypatch):
    encounter = SimpleNamespace(id=9, lab_unit_id=3)
    scope = _scope([("patient_encounters", encounter)])
    monkeypatch.setattr(
        "scripts.remidio_lab_unit_repair.resolve_repair_scope",
        lambda db, **kwargs: scope,
    )

    result = preview_repair(object(), project_code="ICMR-VG", binding_id=14, source_lab_unit_id=3, target_lab_unit_id=1)

    assert result.to_dict()["mode"] == "preview"
    assert result.to_dict()["records_to_change"] == 1
    assert encounter.lab_unit_id == 3


def test_apply_rejects_wrong_confirmation_before_mutation(monkeypatch):
    encounter = SimpleNamespace(id=9, lab_unit_id=3)
    scope = _scope([("patient_encounters", encounter)])
    monkeypatch.setattr(
        "scripts.remidio_lab_unit_repair.resolve_repair_scope",
        lambda db, **kwargs: scope,
    )
    db = SimpleNamespace(flush=lambda: pytest.fail("flush must not run"), add=lambda _: pytest.fail("add must not run"))

    with pytest.raises(RemidioLabUnitRepairError, match="Confirmation token"):
        apply_repair(
            db,
            project_code="ICMR-VG",
            binding_id=14,
            source_lab_unit_id=3,
            target_lab_unit_id=1,
            confirmation_token="WRONG",
        )
    assert encounter.lab_unit_id == 3


def test_apply_updates_all_scoped_rows_atomically(monkeypatch):
    encounter = SimpleNamespace(id=9, lab_unit_id=3)
    task = SimpleNamespace(id=77, lab_unit_id=3)
    scope = _scope([("patient_encounters", encounter), ("grading_tasks", task)])
    added = []
    flushed = []
    db = SimpleNamespace(add=added.append, flush=lambda: flushed.append(True))
    monkeypatch.setattr(
        "scripts.remidio_lab_unit_repair.resolve_repair_scope",
        lambda db, **kwargs: scope,
    )

    result = apply_repair(
        db,
        project_code="ICMR-VG",
        binding_id=14,
        source_lab_unit_id=3,
        target_lab_unit_id=1,
        confirmation_token=scope.confirmation_token,
    )

    assert encounter.lab_unit_id == 1
    assert task.lab_unit_id == 1
    assert added == [encounter, task]
    assert flushed == [True]
    assert result.to_dict(applied=True)["records_to_change"] == 2


def test_unexpected_lineage_is_refused():
    row = SimpleNamespace(id=55, lab_unit_id=9)
    record = _LabRecord("grading_tasks", row.id, row, row.lab_unit_id)

    with pytest.raises(RemidioLabUnitRepairError, match="mixed or unknown lineage"):
        _validate_lab_lineage([record], source_lab_unit_id=3, target_lab_unit_id=1)


def test_apply_is_idempotent_with_same_scope_token(monkeypatch):
    encounter = SimpleNamespace(id=9, lab_unit_id=3)
    task = SimpleNamespace(id=77, lab_unit_id=3)
    calls = []

    def resolve(db, **kwargs):
        calls.append(True)
        return _scope([("patient_encounters", encounter), ("grading_tasks", task)])

    added = []
    monkeypatch.setattr("scripts.remidio_lab_unit_repair.resolve_repair_scope", resolve)
    db = SimpleNamespace(add=added.append, flush=lambda: None)
    token = resolve(db).confirmation_token

    apply_repair(db, project_code="ICMR-VG", binding_id=14, source_lab_unit_id=3, target_lab_unit_id=1, confirmation_token=token)
    apply_repair(db, project_code="ICMR-VG", binding_id=14, source_lab_unit_id=3, target_lab_unit_id=1, confirmation_token=token)

    assert encounter.lab_unit_id == 1
    assert task.lab_unit_id == 1
    assert len(calls) == 3
