#!/usr/bin/env python3
"""Add user_id column to flask_sessions table."""
from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import engine  # noqa: E402

TABLE_NAME = "flask_sessions"
COLUMN_NAME = "user_id"
INDEX_NAME = "ix_flask_sessions_user_id"


def column_exists() -> bool:
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(TABLE_NAME)]
    return COLUMN_NAME in columns


def add_column() -> None:
    ddl = f"ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} INTEGER REFERENCES users(id) ON DELETE SET NULL"
    index_sql = f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON {TABLE_NAME} ({COLUMN_NAME})"
    with engine.begin() as conn:
        conn.execute(text(ddl))
        conn.execute(text(index_sql))


def main() -> None:
    if column_exists():
        print(f"Column '{COLUMN_NAME}' already exists on '{TABLE_NAME}'. Nothing to do.")
        return

    add_column()
    print(f"Column '{COLUMN_NAME}' added to '{TABLE_NAME}' and indexed.")


if __name__ == "__main__":
    main()
