"""add project grader allocations

Revision ID: 8f7a6b5c4d3e
Revises: 7e6f5a4b3c2d
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "8f7a6b5c4d3e"
down_revision: Union[str, Sequence[str], None] = "7e6f5a4b3c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POLICY_TABLE = "project_grading_allocation_policies"
ALLOCATION_TABLE = "project_grader_allocations"


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _has_index(conn, table_name: str, index_name: str) -> bool:
    if table_name not in _table_names(conn):
        return False
    return any(index["name"] == index_name for index in inspect(conn).get_indexes(table_name))


def _create_index_if_missing(
    conn,
    name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
    postgresql_where=None,
) -> None:
    if table_name in _table_names(conn) and not _has_index(conn, table_name, name):
        op.create_index(
            name,
            table_name,
            columns,
            unique=unique,
            postgresql_where=postgresql_where,
        )


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)
    if POLICY_TABLE not in tables:
        op.create_table(
            POLICY_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("enforcement_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("project_id", name="uq_project_grading_allocation_policy_project"),
        )
    _create_index_if_missing(conn, "ix_project_grading_allocation_policies_enforcement_enabled", POLICY_TABLE, ["enforcement_enabled"])
    _create_index_if_missing(conn, "ix_project_grading_allocation_policies_created_by_user_id", POLICY_TABLE, ["created_by_user_id"])
    _create_index_if_missing(conn, "ix_project_grading_allocation_policies_updated_by_user_id", POLICY_TABLE, ["updated_by_user_id"])

    if ALLOCATION_TABLE not in _table_names(conn):
        op.create_table(
            ALLOCATION_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=True),
            sa.Column("encounter_set_type_id", sa.Integer(), nullable=True),
            sa.Column("capacity", sa.String(length=16), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint(
                "scope IN ('disease_image','disease_encounter','encounter_set_unified')",
                name="ck_project_grader_allocation_scope",
            ),
            sa.CheckConstraint(
                "capacity IN ('resident','arbitrator')",
                name="ck_project_grader_allocation_capacity",
            ),
            sa.CheckConstraint(
                "(scope = 'disease_image' AND disease_id IS NOT NULL AND encounter_set_type_id IS NULL) OR "
                "(scope = 'disease_encounter' AND disease_id IS NOT NULL AND encounter_set_type_id IS NOT NULL) OR "
                "(scope = 'encounter_set_unified' AND disease_id IS NULL AND encounter_set_type_id IS NOT NULL)",
                name="ck_project_grader_allocation_target_shape",
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["encounter_set_type_id"], ["encounter_set_types.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        )

    for index_name, columns in (
        ("ix_project_grader_allocations_project_id", ["project_id"]),
        ("ix_project_grader_allocations_user_id", ["user_id"]),
        ("ix_project_grader_allocations_lab_unit_id", ["lab_unit_id"]),
        ("ix_project_grader_allocations_scope", ["scope"]),
        ("ix_project_grader_allocations_disease_id", ["disease_id"]),
        ("ix_project_grader_allocations_encounter_set_type_id", ["encounter_set_type_id"]),
        ("ix_project_grader_allocations_capacity", ["capacity"]),
        ("ix_project_grader_allocations_active", ["active"]),
        ("ix_project_grader_allocations_created_by_user_id", ["created_by_user_id"]),
        ("ix_project_grader_allocations_updated_by_user_id", ["updated_by_user_id"]),
    ):
        _create_index_if_missing(conn, index_name, ALLOCATION_TABLE, columns)
    _create_index_if_missing(
        conn,
        "ix_project_grader_allocation_lookup",
        ALLOCATION_TABLE,
        ["project_id", "lab_unit_id", "scope", "capacity", "active"],
    )
    _create_index_if_missing(
        conn,
        "uq_project_grader_allocation_image",
        ALLOCATION_TABLE,
        ["project_id", "user_id", "lab_unit_id", "disease_id", "capacity"],
        unique=True,
        postgresql_where=sa.text("scope = 'disease_image'"),
    )
    _create_index_if_missing(
        conn,
        "uq_project_grader_allocation_disease_encounter",
        ALLOCATION_TABLE,
        ["project_id", "user_id", "lab_unit_id", "encounter_set_type_id", "disease_id", "capacity"],
        unique=True,
        postgresql_where=sa.text("scope = 'disease_encounter'"),
    )
    _create_index_if_missing(
        conn,
        "uq_project_grader_allocation_unified",
        ALLOCATION_TABLE,
        ["project_id", "user_id", "lab_unit_id", "encounter_set_type_id", "capacity"],
        unique=True,
        postgresql_where=sa.text("scope = 'encounter_set_unified'"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if ALLOCATION_TABLE in _table_names(conn):
        op.drop_table(ALLOCATION_TABLE)
    if POLICY_TABLE in _table_names(conn):
        op.drop_table(POLICY_TABLE)
