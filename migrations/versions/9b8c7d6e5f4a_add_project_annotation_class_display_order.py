"""add project annotation class display order

Revision ID: 9b8c7d6e5f4a
Revises: 8a7b6c5d4e3f
Create Date: 2026-08-02 23:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b8c7d6e5f4a"
down_revision: Union[str, Sequence[str], None] = "8a7b6c5d4e3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "project_annotation_classes"
COLUMN_NAME = "display_order"
CHECK_NAME = "ck_project_annotation_class_display_order"
INDEX_NAME = "ix_project_annotation_classes_policy_order"


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    added_column = COLUMN_NAME not in column_names
    if added_column:
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.Integer(), server_default="0", nullable=False),
        )
        op.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        (ROW_NUMBER() OVER (
                            PARTITION BY policy_id
                            ORDER BY key, id
                        ) - 1) * 10 AS resolved_order
                    FROM project_annotation_classes
                )
                UPDATE project_annotation_classes AS project_class
                SET display_order = ranked.resolved_order
                FROM ranked
                WHERE project_class.id = ranked.id
                """
            )
        )

    inspector = _inspector()
    check_names = {
        check["name"]
        for check in inspector.get_check_constraints(TABLE_NAME)
        if check.get("name")
    }
    if CHECK_NAME not in check_names:
        op.create_check_constraint(CHECK_NAME, TABLE_NAME, "display_order >= 0")

    inspector = _inspector()
    index_names = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}
    if INDEX_NAME not in index_names:
        op.create_index(INDEX_NAME, TABLE_NAME, ["policy_id", "display_order"])


def downgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return

    index_names = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}
    if INDEX_NAME in index_names:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)

    inspector = _inspector()
    check_names = {
        check["name"]
        for check in inspector.get_check_constraints(TABLE_NAME)
        if check.get("name")
    }
    if CHECK_NAME in check_names:
        op.drop_constraint(CHECK_NAME, TABLE_NAME, type_="check")

    inspector = _inspector()
    column_names = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    if COLUMN_NAME in column_names:
        op.drop_column(TABLE_NAME, COLUMN_NAME)
