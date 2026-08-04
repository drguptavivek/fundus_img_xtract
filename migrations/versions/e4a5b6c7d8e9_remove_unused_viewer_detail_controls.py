"""remove unused viewer detail controls

Revision ID: e4a5b6c7d8e9
Revises: d3f4a5b6c7e8
Create Date: 2026-08-04 08:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "d3f4a5b6c7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "viewer_presets"
TUNING_CHECK = "ck_viewer_presets_clinical_tuning_range"
REMOVED_COLUMNS = {
    "highlight_protection": (sa.Float(), "0.0"),
    "local_contrast": (sa.Float(), "0.0"),
    "denoise": (sa.Float(), "0.0"),
    "sharpen": (sa.Float(), "0.0"),
}


def _inspector():
    return sa.inspect(op.get_bind())


def _drop_tuning_check_if_present() -> None:
    checks = {item.get("name") for item in _inspector().get_check_constraints(TABLE_NAME)}
    if TUNING_CHECK in checks:
        op.drop_constraint(TUNING_CHECK, TABLE_NAME, type_="check")


def _reduced_constraint() -> str:
    return (
        "gamma >= 0.35 AND gamma <= 2.5 AND black_point >= -0.2 AND black_point <= 0.25 AND "
        "white_point >= 0.5 AND white_point <= 1.2 AND shadow_lift >= 0 AND shadow_lift <= 1 AND "
        "flattening >= 0 AND flattening <= 1"
    )


def _previous_constraint() -> str:
    return (
        "gamma >= 0.35 AND gamma <= 2.5 AND black_point >= -0.2 AND black_point <= 0.25 AND "
        "white_point >= 0.5 AND white_point <= 1.2 AND highlight_protection >= 0 AND highlight_protection <= 1 AND "
        "shadow_lift >= 0 AND shadow_lift <= 1 AND "
        "flattening >= 0 AND flattening <= 1 AND local_contrast >= 0 AND local_contrast <= 1 AND "
        "denoise >= 0 AND denoise <= 1 AND sharpen >= 0 AND sharpen <= 1"
    )


def upgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return
    _drop_tuning_check_if_present()
    columns = {column["name"] for column in _inspector().get_columns(TABLE_NAME)}
    for name in REMOVED_COLUMNS:
        if name in columns:
            op.drop_column(TABLE_NAME, name)
    op.create_check_constraint(TUNING_CHECK, TABLE_NAME, _reduced_constraint())


def downgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return
    _drop_tuning_check_if_present()
    columns = {column["name"] for column in _inspector().get_columns(TABLE_NAME)}
    for name, (column_type, default) in REMOVED_COLUMNS.items():
        if name not in columns:
            op.add_column(
                TABLE_NAME,
                sa.Column(name, column_type, server_default=default, nullable=False),
            )
    op.create_check_constraint(TUNING_CHECK, TABLE_NAME, _previous_constraint())
