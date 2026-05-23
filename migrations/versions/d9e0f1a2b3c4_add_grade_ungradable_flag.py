"""add grade ungradable flag

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "disease_gradings"
COLUMN_NAME = "is_ungradable"


def _columns(conn) -> set[str]:
    if TABLE_NAME not in inspect(conn).get_table_names():
        return set()
    return {column["name"] for column in inspect(conn).get_columns(TABLE_NAME)}


def upgrade() -> None:
    conn = op.get_bind()
    if COLUMN_NAME in _columns(conn):
        return
    op.add_column(
        TABLE_NAME,
        sa.Column(COLUMN_NAME, sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if COLUMN_NAME not in _columns(conn):
        return
    op.drop_column(TABLE_NAME, COLUMN_NAME)
