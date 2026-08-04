"""add clinical viewer tuning

Revision ID: b1d2e3f4a5c6
Revises: a0c1d2e3f4b5
Create Date: 2026-08-03 12:55:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1d2e3f4a5c6"
down_revision: Union[str, Sequence[str], None] = "a0c1d2e3f4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "viewer_presets"
FILTER_CHECK = "ck_viewer_presets_filter"
TUNING_CHECK = "ck_viewer_presets_clinical_tuning_range"
COLUMNS = {
    "gamma": (sa.Float(), "1.0"),
    "black_point": (sa.Float(), "0.0"),
    "white_point": (sa.Float(), "1.0"),
    "highlight_protection": (sa.Float(), "0.0"),
    "flattening": (sa.Float(), "0.0"),
    "local_contrast": (sa.Float(), "0.0"),
    "denoise": (sa.Float(), "0.0"),
    "sharpen": (sa.Float(), "0.0"),
    "invert": (sa.Boolean(), sa.false()),
}


def _inspector():
    return sa.inspect(op.get_bind())


def _drop_check_if_present(name: str) -> None:
    checks = {item.get("name") for item in _inspector().get_check_constraints(TABLE_NAME)}
    if name in checks:
        op.drop_constraint(name, TABLE_NAME, type_="check")


def upgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    for name, (column_type, default) in COLUMNS.items():
        if name not in existing:
            op.add_column(TABLE_NAME, sa.Column(name, column_type, server_default=default, nullable=False))

    _drop_check_if_present(FILTER_CHECK)
    op.execute("UPDATE viewer_presets SET filter = 'redfree' WHERE filter IN ('greenboost','greenchannel','redgreenfree')")
    op.execute("UPDATE viewer_presets SET filter = 'bluemono' WHERE filter = 'blueonly'")
    op.execute("UPDATE viewer_presets SET filter = 'none' WHERE filter IN ('gray','contrast','enhance','greenfree')")
    op.create_check_constraint(
        FILTER_CHECK,
        TABLE_NAME,
        "filter IN ('none','redfree','redchannel','bluemono','greenblue','redfreeenhanced')",
    )
    _drop_check_if_present(TUNING_CHECK)
    op.create_check_constraint(
        TUNING_CHECK,
        TABLE_NAME,
        "gamma >= 0.35 AND gamma <= 2.5 AND black_point >= -0.2 AND black_point <= 0.25 AND "
        "white_point >= 0.5 AND white_point <= 1.2 AND highlight_protection >= 0 AND highlight_protection <= 1 AND "
        "flattening >= 0 AND flattening <= 1 AND local_contrast >= 0 AND local_contrast <= 1 AND "
        "denoise >= 0 AND denoise <= 1 AND sharpen >= 0 AND sharpen <= 1",
    )


def downgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return
    _drop_check_if_present(TUNING_CHECK)
    _drop_check_if_present(FILTER_CHECK)
    op.execute("UPDATE viewer_presets SET filter = 'none' WHERE filter IN ('redchannel','greenblue','redfreeenhanced')")
    op.create_check_constraint(
        FILTER_CHECK,
        TABLE_NAME,
        "filter IN ('none','redfree','greenboost','bluemono','gray','contrast','enhance','greenchannel','blueonly','redgreenfree','greenfree')",
    )
    existing = {column["name"] for column in _inspector().get_columns(TABLE_NAME)}
    for name in reversed(tuple(COLUMNS)):
        if name in existing:
            op.drop_column(TABLE_NAME, name)
