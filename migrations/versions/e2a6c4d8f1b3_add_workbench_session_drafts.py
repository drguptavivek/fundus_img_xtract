"""add workbench session drafts

Revision ID: e2a6c4d8f1b3
Revises: d8e4f1a2b3c5
Create Date: 2026-08-11 10:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e2a6c4d8f1b3"
down_revision: Union[str, Sequence[str], None] = "d8e4f1a2b3c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "grading_workbench_sessions"


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if TABLE_NAME not in inspector.get_table_names():
        return set()
    return {item["name"] for item in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    columns = _columns()
    if "draft_observations_json" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column(
                "draft_observations_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
    if "draft_updated_at" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("draft_updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    columns = _columns()
    if "draft_updated_at" in columns:
        op.drop_column(TABLE_NAME, "draft_updated_at")
    if "draft_observations_json" in columns:
        op.drop_column(TABLE_NAME, "draft_observations_json")
