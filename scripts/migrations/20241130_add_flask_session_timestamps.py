#!/usr/bin/env python3
"""Add started_at and ended_at columns to flask_sessions."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import engine  # noqa: E402

TABLE_NAME = "flask_sessions"
STARTED_AT = "started_at"
ENDED_AT = "ended_at"


def _column_names() -> set[str]:
    inspector = inspect(engine)
    return {col["name"] for col in inspector.get_columns(TABLE_NAME)}


def _table_exists() -> bool:
    inspector = inspect(engine)
    return TABLE_NAME in inspector.get_table_names()


def _add_started_at(dialect: str) -> None:
    if dialect == "sqlite":
        ddl = (
            f"ALTER TABLE {TABLE_NAME} "
            "ADD COLUMN started_at TIMESTAMP NOT NULL "
            "DEFAULT '1970-01-01 00:00:00+00:00'"
        )
        with engine.begin() as conn:
            conn.execute(text(ddl))
    else:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {TABLE_NAME} "
                    "ADD COLUMN started_at TIMESTAMP WITH TIME ZONE"
                )
            )
            conn.execute(
                text(
                    f"UPDATE {TABLE_NAME} SET started_at = COALESCE(started_at, expiry)"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {TABLE_NAME} "
                    "ALTER COLUMN started_at SET NOT NULL"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE {TABLE_NAME} "
                    "ALTER COLUMN started_at SET DEFAULT TIMEZONE('UTC', NOW())"
                )
            )


def _add_ended_at(dialect: str) -> None:
    ddl = (
        f"ALTER TABLE {TABLE_NAME} ADD COLUMN ended_at "
        "TIMESTAMP" + (" WITH TIME ZONE" if dialect != "sqlite" else "")
    )
    with engine.begin() as conn:
        conn.execute(text(ddl))


def _backfill_sqlite_started_at() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"UPDATE {TABLE_NAME} "
                "SET started_at = CASE "
                "WHEN started_at IS NULL OR started_at = '1970-01-01 00:00:00+00:00' "
                f"THEN COALESCE(expiry, CURRENT_TIMESTAMP) "
                "ELSE started_at END"
            )
        )


def main() -> None:
    if not _table_exists():
        print("Table 'flask_sessions' does not exist; run the earlier session migrations first.")
        return

    existing_columns = _column_names()
    dialect = engine.dialect.name

    if STARTED_AT not in existing_columns:
        _add_started_at(dialect)
        if dialect == "sqlite":
            _backfill_sqlite_started_at()
        print("Column 'started_at' added to 'flask_sessions'.")
    else:
        print("Column 'started_at' already present; skipping.")

    if ENDED_AT not in existing_columns:
        _add_ended_at(dialect)
        print("Column 'ended_at' added to 'flask_sessions'.")
    else:
        print("Column 'ended_at' already present; skipping.")


if __name__ == "__main__":
    main()
