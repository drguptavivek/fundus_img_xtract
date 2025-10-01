#!/usr/bin/env python3
"""Create notification_reads table for per-user notification read tracking."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import engine  # noqa: E402

TABLE_NAME = "notification_reads"


def table_exists() -> bool:
    inspector = inspect(engine)
    return TABLE_NAME in inspector.get_table_names()


def create_table() -> None:
    ddl = """
        CREATE TABLE notification_reads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            read_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_notification_reads_notification_user UNIQUE (notification_id, user_id)
        )
    """
    idx_notification = "CREATE INDEX IF NOT EXISTS ix_notification_reads_notification_id ON notification_reads (notification_id)"
    idx_user = "CREATE INDEX IF NOT EXISTS ix_notification_reads_user_id ON notification_reads (user_id)"
    with engine.begin() as conn:
        conn.execute(text(ddl))
        conn.execute(text(idx_notification))
        conn.execute(text(idx_user))


def main() -> None:
    if table_exists():
        print("Table 'notification_reads' already exists. Nothing to do.")
        return

    create_table()
    print("Table 'notification_reads' created successfully.")


if __name__ == "__main__":
    main()
