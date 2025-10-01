#!/usr/bin/env python3
"""Add lab_unit_id column to jobs table."""
from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import engine  # noqa: E402

TABLE_NAME = "jobs"
COLUMN_NAME = "lab_unit_id"
COLUMN_TYPE = "INTEGER"
INDEX_NAME = "ix_jobs_lab_unit_id"


def column_exists() -> bool:
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(TABLE_NAME)]
    return COLUMN_NAME in columns


def add_column() -> None:
    ddl = f"ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} {COLUMN_TYPE}"
    with engine.begin() as conn:
        conn.execute(text(ddl))
        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON {TABLE_NAME} ({COLUMN_NAME})"))


def main() -> None:
    if column_exists():
        print(f"Column '{COLUMN_NAME}' already exists on '{TABLE_NAME}'. Nothing to do.")
        return

    add_column()
    print(f"Column '{COLUMN_NAME}' added to '{TABLE_NAME}' and indexed.")


if __name__ == "__main__":
    main()
