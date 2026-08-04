"""add protected shadow lift

Revision ID: d3f4a5b6c7e8
Revises: c2e3f4a5b6d7
Create Date: 2026-08-03 18:12:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f4a5b6c7e8"
down_revision: Union[str, Sequence[str], None] = "c2e3f4a5b6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "viewer_presets"
FILTER_CHECK = "ck_viewer_presets_filter"
TUNING_CHECK = "ck_viewer_presets_clinical_tuning_range"


def _inspector():
    return sa.inspect(op.get_bind())


def _drop_check_if_present(name: str) -> None:
    checks = {item.get("name") for item in _inspector().get_check_constraints(TABLE_NAME)}
    if name in checks:
        op.drop_constraint(name, TABLE_NAME, type_="check")


def _clinical_tuning_constraint(include_shadow_lift: bool) -> str:
    shadow_lift = "shadow_lift >= 0 AND shadow_lift <= 1 AND " if include_shadow_lift else ""
    return (
        "gamma >= 0.35 AND gamma <= 2.5 AND black_point >= -0.2 AND black_point <= 0.25 AND "
        "white_point >= 0.5 AND white_point <= 1.2 AND highlight_protection >= 0 AND highlight_protection <= 1 AND "
        f"{shadow_lift}"
        "flattening >= 0 AND flattening <= 1 AND local_contrast >= 0 AND local_contrast <= 1 AND "
        "denoise >= 0 AND denoise <= 1 AND sharpen >= 0 AND sharpen <= 1"
    )


def upgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    if "shadow_lift" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("shadow_lift", sa.Float(), server_default="0.0", nullable=False),
        )

    _drop_check_if_present(FILTER_CHECK)
    op.execute(
        "UPDATE viewer_presets SET filter = 'none' "
        "WHERE filter NOT IN ('none','enhance','redfree','redfreeenhanced')"
    )
    op.create_check_constraint(
        FILTER_CHECK,
        TABLE_NAME,
        "filter IN ('none','enhance','redfree','redfreeenhanced')",
    )
    _drop_check_if_present(TUNING_CHECK)
    op.create_check_constraint(
        TUNING_CHECK,
        TABLE_NAME,
        _clinical_tuning_constraint(include_shadow_lift=True),
    )


def downgrade() -> None:
    inspector = _inspector()
    if TABLE_NAME not in inspector.get_table_names():
        return
    _drop_check_if_present(TUNING_CHECK)
    _drop_check_if_present(FILTER_CHECK)
    op.execute("UPDATE viewer_presets SET filter = 'none' WHERE filter = 'enhance'")
    op.create_check_constraint(
        FILTER_CHECK,
        TABLE_NAME,
        "filter IN ('none','redfree','redchannel','greenchannel','bluemono','greenblue','redfreeenhanced')",
    )
    columns = {column["name"] for column in _inspector().get_columns(TABLE_NAME)}
    if "shadow_lift" in columns:
        op.drop_column(TABLE_NAME, "shadow_lift")
    op.create_check_constraint(
        TUNING_CHECK,
        TABLE_NAME,
        _clinical_tuning_constraint(include_shadow_lift=False),
    )
