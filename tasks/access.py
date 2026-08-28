"""Authorization lineage for grading tasks."""

from __future__ import annotations

from sqlalchemy import select

from authz import AuthorizationDenied, RecordColumns, RecordScope


def task_record_scope(context, task) -> RecordScope:
    """Resolve a task's maintained project and Lab Unit lineage."""
    lab_unit_id = getattr(task, "lab_unit_id", None)
    if lab_unit_id is None:
        raise AuthorizationDenied("task_lab_unit_missing")

    from models import LabUnit

    hospital_id = context.db.execute(
        select(LabUnit.hospital_id).where(LabUnit.id == int(lab_unit_id))
    ).scalar_one_or_none()
    if hospital_id is None:
        raise AuthorizationDenied("task_hospital_lineage_missing")

    project_id = getattr(task, "project_id", None)
    if project_id is None:
        return RecordScope.classical(
            lab_unit_id=lab_unit_id,
            hospital_id=hospital_id,
        )
    return RecordScope.project(
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        hospital_id=hospital_id,
    )


def task_columns(model, *, hospital_id_column=None) -> RecordColumns:
    """Columns for a task query; callers join LabUnit for hospital paths."""
    if not all(hasattr(model, name) for name in ("project_id", "lab_unit_id")):
        return RecordColumns()
    return RecordColumns(
        project_id=model.project_id,
        hospital_id=hospital_id_column,
        lab_unit_id=model.lab_unit_id,
    )
