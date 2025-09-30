#!/usr/bin/env python3
"""Add timezone column to users table and backfill existing records."""
from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import inspect, text


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import engine
from utils.timezone_choices import DEFAULT_TIMEZONE

TABLE_NAME = "users"
COLUMN_NAME = "timezone"
COLUMN_TYPE = "VARCHAR(64)"


def column_exists() -> bool:
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(TABLE_NAME)]
    return COLUMN_NAME in columns


def add_column() -> None:
    ddl = f"ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} {COLUMN_TYPE}"
    with engine.begin() as conn:
        conn.execute(text(ddl))
        conn.execute(
            text(f"UPDATE {TABLE_NAME} SET {COLUMN_NAME} = :tz WHERE {COLUMN_NAME} IS NULL"),
            {"tz": DEFAULT_TIMEZONE},
        )


def main() -> None:
    if column_exists():
        print(f"Column '{COLUMN_NAME}' already exists on '{TABLE_NAME}'. Nothing to do.")
        return

    add_column()
    print(f"Column '{COLUMN_NAME}' added to '{TABLE_NAME}' and defaulted to '{DEFAULT_TIMEZONE}'.")


if __name__ == "__main__":
    main()
