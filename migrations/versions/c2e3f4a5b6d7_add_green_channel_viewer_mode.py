"""add green channel viewer mode

Revision ID: c2e3f4a5b6d7
Revises: b1d2e3f4a5c6
Create Date: 2026-08-03 17:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2e3f4a5b6d7"
down_revision: Union[str, Sequence[str], None] = "b1d2e3f4a5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "viewer_presets"
CHECK_NAME = "ck_viewer_presets_filter"


def _has_table() -> bool:
    return TABLE_NAME in sa.inspect(op.get_bind()).get_table_names()


def _drop_check() -> None:
    checks = {item.get("name") for item in sa.inspect(op.get_bind()).get_check_constraints(TABLE_NAME)}
    if CHECK_NAME in checks:
        op.drop_constraint(CHECK_NAME, TABLE_NAME, type_="check")


def upgrade() -> None:
    if not _has_table():
        return
    _drop_check()
    op.create_check_constraint(
        CHECK_NAME,
        TABLE_NAME,
        "filter IN ('none','redfree','redchannel','greenchannel','bluemono','greenblue','redfreeenhanced')",
    )


def downgrade() -> None:
    if not _has_table():
        return
    _drop_check()
    op.execute("UPDATE viewer_presets SET filter = 'redfree' WHERE filter = 'greenchannel'")
    op.create_check_constraint(
        CHECK_NAME,
        TABLE_NAME,
        "filter IN ('none','redfree','redchannel','bluemono','greenblue','redfreeenhanced')",
    )
