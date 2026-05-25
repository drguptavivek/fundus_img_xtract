"""Add Remidio ZIP EncounterSet profile flag.

Revision ID: 9b7e6a5d4c3f
Revises: f2a3b4c5d6e7
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "9b7e6a5d4c3f"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


TABLE = "upload_profiles"
COLUMN = "allow_remidio_zip_encounter_set"


def _column_names(conn) -> set[str]:
    if TABLE not in inspect(conn).get_table_names():
        return set()
    return {column["name"] for column in inspect(conn).get_columns(TABLE)}


def upgrade():
    conn = op.get_bind()
    if COLUMN not in _column_names(conn):
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade():
    conn = op.get_bind()
    if COLUMN in _column_names(conn):
        op.drop_column(TABLE, COLUMN)
