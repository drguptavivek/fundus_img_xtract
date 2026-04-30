"""Manual backfill for legacy uploads into the Routine Patient Care project.

This script is intentionally not called from migrations. Run without ``--apply``
to inspect counts, then run with ``--apply`` to create/update the project and set
``project_id`` on legacy upload provenance rows that are still NULL.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable

from sqlalchemy import func

from db_transaction_manager import transaction_scope
from models import (
    DirectImageUpload,
    EncounterFile,
    EncounterFilePDF,
    EncounterSetImage,
    Job,
    PatientEncounters,
    Project,
)

DEFAULT_PROJECT_TITLE = "Routine Patient Care Services"
DEFAULT_PROJECT_CODE = "ROUTINE_PATIENT_CARE"


def _legacy_tables() -> tuple[type, ...]:
    """Return project-provenance models eligible for manual legacy backfill."""
    return (
        Job,
        DirectImageUpload,
        PatientEncounters,
        EncounterFile,
        EncounterFilePDF,
        EncounterSetImage,
    )


def _get_or_create_project(db, *, apply: bool) -> Project | None:
    """Return the routine-care project, creating it only in apply mode."""
    project = db.query(Project).filter(Project.code == DEFAULT_PROJECT_CODE).one_or_none()
    if project or not apply:
        return project

    project = Project(
        title=DEFAULT_PROJECT_TITLE,
        code=DEFAULT_PROJECT_CODE,
        description="Default project for legacy uploads performed as routine patient care services.",
        active=True,
    )
    db.add(project)
    db.flush()
    return project


def _count_null_project_rows(db, models: Iterable[type]) -> dict[str, int]:
    """Count rows that still lack project provenance for each model."""
    return {
        model.__tablename__: db.query(func.count(model.id)).filter(model.project_id.is_(None)).scalar() or 0
        for model in models
    }


def run_backfill(*, apply: bool) -> dict[str, object]:
    """Run the dry-run or apply-mode routine-care project backfill."""
    with transaction_scope() as db:
        models = _legacy_tables()
        project = _get_or_create_project(db, apply=apply)
        counts = _count_null_project_rows(db, models)
        updated: dict[str, int] = {}

        if apply:
            if project is None:
                raise RuntimeError("Routine Patient Care Services project could not be created.")
            for model in models:
                updated[model.__tablename__] = (
                    db.query(model)
                    .filter(model.project_id.is_(None))
                    .update({model.project_id: project.id}, synchronize_session=False)
                )

        return {
            "apply": apply,
            "project_id": project.id if project else None,
            "project_code": DEFAULT_PROJECT_CODE,
            "null_project_counts": counts,
            "updated_counts": updated,
        }


def main() -> None:
    """Parse CLI arguments and print a compact backfill summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist the Routine Patient Care Services backfill.")
    args = parser.parse_args()

    result = run_backfill(apply=args.apply)
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: {result['project_code']} project_id={result['project_id']}")
    for table_name, count in result["null_project_counts"].items():
        updated = result["updated_counts"].get(table_name, 0)
        print(f"{table_name}: null_project_rows={count} updated={updated}")


if __name__ == "__main__":
    main()
