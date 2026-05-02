"""add ai model disease links

Revision ID: a6d4c9e8b1f0
Revises: f5b8c1d2e3a4
Create Date: 2026-05-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "a6d4c9e8b1f0"
down_revision: Union[str, Sequence[str], None] = "f5b8c1d2e3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _has_index(conn, table_name: str, index_name: str) -> bool:
    return op.get_context().dialect.has_index(conn, table_name, index_name)


def _create_index(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if table_name in _tables(conn) and not _has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    conn = op.get_bind()
    if "ai_model_diseases" not in _tables(conn):
        op.create_table(
            "ai_model_diseases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="CASCADE", name="fk_ai_model_diseases_ai_model"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="CASCADE", name="fk_ai_model_diseases_disease"),
            sa.UniqueConstraint("ai_model_id", "disease_id", name="uq_ai_model_disease"),
        )
    _create_index(conn, "ix_ai_model_diseases_ai_model_id", "ai_model_diseases", ["ai_model_id"])
    _create_index(conn, "ix_ai_model_diseases_disease_id", "ai_model_diseases", ["disease_id"])
    _create_index(conn, "ix_ai_model_diseases_active", "ai_model_diseases", ["active"])
    _create_index(conn, "ix_ai_model_diseases_disease_active", "ai_model_diseases", ["disease_id", "active"])

    conn.execute(
        text(
            """
            INSERT INTO ai_model_diseases (ai_model_id, disease_id, active, created_at)
            SELECT i.ai_model_id, d.id, true, now()
            FROM ai_model_integrations i
            JOIN diseases d ON lower(d.name) = 'glaucoma'
            WHERE i.provider = 'wadhwani_glaucoma'
            ON CONFLICT (ai_model_id, disease_id) DO UPDATE SET active = true
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if "ai_model_diseases" in _tables(conn):
        op.drop_table("ai_model_diseases")
