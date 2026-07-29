"""add encounter set image referral flag

Revision ID: f3a5c7d9e1b2
Revises: e2f4a6b8c0d1
Create Date: 2026-07-29 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f3a5c7d9e1b2"
down_revision = "e2f4a6b8c0d1"
branch_labels = None
depends_on = None


TABLE = "encounter_set_images"
VALUE_COLUMN = "referral_needed_or_positive_image"
UPDATED_AT_COLUMN = "referral_needed_or_positive_image_updated_at"
INDEX_NAME = f"ix_{TABLE}_{VALUE_COLUMN}"
CHECK_NAME = "ck_encounter_set_images_referral_needed_or_positive_image"


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).first()
    )


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_name = :table_name
                  AND constraint_name = :constraint_name
                """
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        ).first()
    )


def _index_exists(conn, index_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :index_name"),
            {"index_name": index_name},
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, TABLE, VALUE_COLUMN):
        op.add_column(
            TABLE,
            sa.Column(VALUE_COLUMN, sa.String(length=16), nullable=False, server_default="missing"),
        )
    if not _column_exists(conn, TABLE, UPDATED_AT_COLUMN):
        op.add_column(TABLE, sa.Column(UPDATED_AT_COLUMN, sa.DateTime(timezone=True), nullable=True))
    if not _index_exists(conn, INDEX_NAME):
        op.create_index(INDEX_NAME, TABLE, [VALUE_COLUMN], unique=False)
    if not _constraint_exists(conn, TABLE, CHECK_NAME):
        op.create_check_constraint(
            CHECK_NAME,
            TABLE,
            f"{VALUE_COLUMN} IN ('yes','no','missing')",
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _constraint_exists(conn, TABLE, CHECK_NAME):
        op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    if _index_exists(conn, INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name=TABLE)
    if _column_exists(conn, TABLE, UPDATED_AT_COLUMN):
        op.drop_column(TABLE, UPDATED_AT_COLUMN)
    if _column_exists(conn, TABLE, VALUE_COLUMN):
        op.drop_column(TABLE, VALUE_COLUMN)
