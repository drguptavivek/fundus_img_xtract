"""add project EncounterSet permissions

Revision ID: d9f5a2b3c4d6
Revises: d8e4f1a2b3c5
Create Date: 2026-08-11 09:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9f5a2b3c4d6"
down_revision: Union[str, Sequence[str], None] = "d8e4f1a2b3c5"
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
    table = "project_encounter_set_permissions"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("can_browse", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("can_verify", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "project_id", "user_id", "lab_unit_id",
                name="uq_project_encounter_set_permission",
            ),
        )
    indexes = {
        "ix_project_encounter_set_permissions_project_id": ["project_id"],
        "ix_project_encounter_set_permissions_user_id": ["user_id"],
        "ix_project_encounter_set_permissions_lab_unit_id": ["lab_unit_id"],
        "ix_project_encounter_set_permissions_active": ["active"],
        "ix_project_encounter_set_permissions_lookup": ["user_id", "project_id", "lab_unit_id", "active"],
    }
    for name, columns in indexes.items():
        if name not in _indexes(table):
            op.create_index(name, table, columns)


def downgrade() -> None:
    table = "project_encounter_set_permissions"
    if table not in _tables():
        return
    for name in (
        "ix_project_encounter_set_permissions_lookup",
        "ix_project_encounter_set_permissions_active",
        "ix_project_encounter_set_permissions_lab_unit_id",
        "ix_project_encounter_set_permissions_user_id",
        "ix_project_encounter_set_permissions_project_id",
    ):
        if name in _indexes(table):
            op.drop_index(name, table_name=table)
    op.drop_table(table)
