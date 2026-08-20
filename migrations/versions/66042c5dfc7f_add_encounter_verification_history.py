"""add encounter verification history

Revision ID: 66042c5dfc7f
Revises: 86059f1ec14b
Create Date: 2026-08-20 07:56:15.510281

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '66042c5dfc7f'
down_revision: Union[str, Sequence[str], None] = '86059f1ec14b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "encounter_verification_history"
INDEX_NAME = "ix_encounter_verification_history_encounter_occurred"


def _table_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    return TABLE_NAME in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    if _table_exists():
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "patient_encounter_id",
            sa.Integer(),
            sa.ForeignKey("patient_encounters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action_type IN ('reopened','metadata_corrected','reverified')",
            name="ck_encounter_verification_history_action_type",
        ),
    )
    op.create_index(
        op.f("ix_encounter_verification_history_patient_encounter_id"),
        TABLE_NAME,
        ["patient_encounter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_encounter_verification_history_action_type"),
        TABLE_NAME,
        ["action_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_encounter_verification_history_actor_user_id"),
        TABLE_NAME,
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["patient_encounter_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    if not _table_exists():
        return
    op.drop_table(TABLE_NAME)
