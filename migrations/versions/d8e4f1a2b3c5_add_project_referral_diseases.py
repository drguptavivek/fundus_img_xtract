"""add project referral diseases

Revision ID: d8e4f1a2b3c5
Revises: c79d5af492ef
Create Date: 2026-08-11 08:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e4f1a2b3c5"
down_revision: Union[str, Sequence[str], None] = "c79d5af492ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _indexes(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {item["name"] for item in _inspector().get_indexes(table_name)}


def upgrade() -> None:
    if "project_referral_diseases" not in _tables():
        op.create_table(
            "project_referral_diseases",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "disease_id", name="uq_project_referral_disease"),
        )
    if "ix_project_referral_diseases_project_id" not in _indexes("project_referral_diseases"):
        op.create_index(
            "ix_project_referral_diseases_project_id",
            "project_referral_diseases",
            ["project_id"],
        )
    if "ix_project_referral_diseases_disease_id" not in _indexes("project_referral_diseases"):
        op.create_index(
            "ix_project_referral_diseases_disease_id",
            "project_referral_diseases",
            ["disease_id"],
        )
    if "ix_project_referral_diseases_active" not in _indexes("project_referral_diseases"):
        op.create_index(
            "ix_project_referral_diseases_active",
            "project_referral_diseases",
            ["active"],
        )
    if "ix_project_referral_diseases_project_active" not in _indexes("project_referral_diseases"):
        op.create_index(
            "ix_project_referral_diseases_project_active",
            "project_referral_diseases",
            ["project_id", "active"],
        )


def downgrade() -> None:
    if "project_referral_diseases" not in _tables():
        return
    for index_name in (
        "ix_project_referral_diseases_project_active",
        "ix_project_referral_diseases_active",
        "ix_project_referral_diseases_disease_id",
        "ix_project_referral_diseases_project_id",
    ):
        if index_name in _indexes("project_referral_diseases"):
            op.drop_index(index_name, table_name="project_referral_diseases")
    op.drop_table("project_referral_diseases")
