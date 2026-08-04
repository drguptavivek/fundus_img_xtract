"""add viewer preset color tuning

Revision ID: a0c1d2e3f4b5
Revises: 9b8c7d6e5f4a
Create Date: 2026-08-03 09:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0c1d2e3f4b5"
down_revision: Union[str, Sequence[str], None] = "9b8c7d6e5f4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "viewer_presets"
CHECK_NAME = "ck_viewer_presets_color_tuning_range"
COLUMNS = (
    "saturation",
    "red_luminance",
    "red_saturation",
    "green_luminance",
    "green_saturation",
    "blue_luminance",
    "blue_saturation",
)


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    for column_name in COLUMNS:
        if column_name not in column_names:
            op.add_column(
                TABLE_NAME,
                sa.Column(column_name, sa.Float(), server_default="1.0", nullable=False),
            )

    inspector = _inspector()
    check_names = {
        check["name"]
        for check in inspector.get_check_constraints(TABLE_NAME)
        if check.get("name")
    }
    if CHECK_NAME not in check_names:
        expression = " AND ".join(f"{column} >= 0 AND {column} <= 3.0" for column in COLUMNS)
        op.create_check_constraint(CHECK_NAME, TABLE_NAME, expression)


def downgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return

    check_names = {
        check["name"]
        for check in inspector.get_check_constraints(TABLE_NAME)
        if check.get("name")
    }
    if CHECK_NAME in check_names:
        op.drop_constraint(CHECK_NAME, TABLE_NAME, type_="check")

    column_names = {column["name"] for column in _inspector().get_columns(TABLE_NAME)}
    for column_name in reversed(COLUMNS):
        if column_name in column_names:
            op.drop_column(TABLE_NAME, column_name)
