"""Add IITK ZIP EncounterSet profile flag.

Revision ID: c9d8e7f6a5b4
Revises: e7a8b9c0d1e2
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c9d8e7f6a5b4"
down_revision = "e7a8b9c0d1e2"
branch_labels = None
depends_on = None


TABLE = "upload_profiles"
COLUMN = "allow_iitk_zip_encounter_set"


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
