#!/usr/bin/env python3
"""Create flask_sessions table for server-side session storage."""
from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import engine  # noqa: E402

TABLE_NAME = "flask_sessions"


def table_exists() -> bool:
    inspector = inspect(engine)
    return TABLE_NAME in inspector.get_table_names()


def create_table() -> None:
    create_sql = text(
        """
        CREATE TABLE flask_sessions (
            session_id VARCHAR(255) PRIMARY KEY,
            data TEXT NOT NULL,
            expiry TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    index_sql = text("CREATE INDEX IF NOT EXISTS ix_flask_sessions_expiry ON flask_sessions (expiry)")
    with engine.begin() as conn:
        conn.execute(create_sql)
        conn.execute(index_sql)


def main() -> None:
    if table_exists():
        print("Table 'flask_sessions' already exists. Nothing to do.")
        return

    create_table()
    print("Table 'flask_sessions' created successfully.")


if __name__ == "__main__":
    main()
