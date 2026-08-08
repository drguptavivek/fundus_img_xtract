"""add review grade correction archive

Revision ID: 536dcee9e7de
Revises: 8f7a6b5c4d3e
Create Date: 2026-08-08 05:35:10.056491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "536dcee9e7de"
down_revision: Union[str, Sequence[str], None] = "8f7a6b5c4d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "review_grade_correction_archive"


def _table_names(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _index_names(conn) -> set[str]:
    if TABLE_NAME not in _table_names(conn):
        return set()
    return {index["name"] for index in sa.inspect(conn).get_indexes(TABLE_NAME)}


def _create_index_if_missing(conn, name: str, columns: list[str]) -> None:
    if TABLE_NAME in _table_names(conn) and name not in _index_names(conn):
        op.create_index(name, TABLE_NAME, columns)


def upgrade() -> None:
    """Create the immutable archive used by the one-time review correction."""
    conn = op.get_bind()
    if TABLE_NAME not in _table_names(conn):
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("original_grade_id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("migration_id", sa.String(length=64), nullable=False),
            sa.Column("script_name", sa.String(length=255), nullable=False),
            sa.Column(
                "archived_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.UniqueConstraint(
                "migration_id",
                "original_grade_id",
                name="uq_review_grade_correction_archive_migration_grade",
            ),
        )

    _create_index_if_missing(
        conn,
        "ix_review_grade_correction_archive_original_grade_id",
        ["original_grade_id"],
    )
    _create_index_if_missing(
        conn,
        "ix_review_grade_correction_archive_task_id",
        ["task_id"],
    )
    _create_index_if_missing(
        conn,
        "ix_review_grade_correction_archive_migration_id",
        ["migration_id"],
    )
    _create_index_if_missing(
        conn,
        "ix_review_grade_correction_archive_archived_at",
        ["archived_at"],
    )


def downgrade() -> None:
    """Remove the correction archive when downgrading before this feature."""
    conn = op.get_bind()
    if TABLE_NAME in _table_names(conn):
        op.drop_table(TABLE_NAME)
