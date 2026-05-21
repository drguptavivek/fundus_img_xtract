"""add encounter set types

Revision ID: e2b7c9a1d4f6
Revises: c4d5e6f7a8b9
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e2b7c9a1d4f6"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _fk_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {fk["name"] for fk in inspect(conn).get_foreign_keys(table_name)}


def _unique_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {constraint["name"] for constraint in inspect(conn).get_unique_constraints(table_name)}


def _create_index_if_missing(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if "encounter_set_types" not in tables:
        op.create_table(
            "encounter_set_types",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("target_scheme_id", sa.Integer(), nullable=False),
            sa.Column("metadata_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{\"fields\": []}'::jsonb")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.UniqueConstraint("project_id", "code", name="uq_encounter_set_types_project_code"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_encounter_set_types_project_id_projects", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["target_scheme_id"], ["diseases.id"], name="fk_encounter_set_types_target_scheme_id_diseases", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_encounter_set_types_created_by_user_id_users", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], name="fk_encounter_set_types_updated_by_user_id_users", ondelete="SET NULL"),
        )
    else:
        columns = _column_names(conn, "encounter_set_types")
        if "code" not in columns:
            op.add_column("encounter_set_types", sa.Column("code", sa.String(length=64), nullable=True))
            op.execute("UPDATE encounter_set_types SET code = regexp_replace(lower(name), '[^a-z0-9_.-]+', '_', 'g') WHERE code IS NULL")
            op.alter_column("encounter_set_types", "code", nullable=False)
        if "description" not in columns:
            op.add_column("encounter_set_types", sa.Column("description", sa.Text(), nullable=True))
        if "created_by_user_id" not in columns:
            op.add_column("encounter_set_types", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        if "updated_by_user_id" not in columns:
            op.add_column("encounter_set_types", sa.Column("updated_by_user_id", sa.Integer(), nullable=True))
        if "metadata_schema_json" in columns:
            op.execute("UPDATE encounter_set_types SET metadata_schema_json = '{\"fields\": []}'::jsonb WHERE metadata_schema_json = '{}'::jsonb")

        fks = _fk_names(conn, "encounter_set_types")
        if "fk_encounter_set_types_project_id_projects" not in fks:
            op.create_foreign_key("fk_encounter_set_types_project_id_projects", "encounter_set_types", "projects", ["project_id"], ["id"], ondelete="CASCADE")
        if "fk_encounter_set_types_target_scheme_id_diseases" not in fks:
            op.create_foreign_key("fk_encounter_set_types_target_scheme_id_diseases", "encounter_set_types", "diseases", ["target_scheme_id"], ["id"], ondelete="RESTRICT")
        if "fk_encounter_set_types_created_by_user_id_users" not in fks:
            op.create_foreign_key("fk_encounter_set_types_created_by_user_id_users", "encounter_set_types", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL")
        if "fk_encounter_set_types_updated_by_user_id_users" not in fks:
            op.create_foreign_key("fk_encounter_set_types_updated_by_user_id_users", "encounter_set_types", "users", ["updated_by_user_id"], ["id"], ondelete="SET NULL")
        if "uq_encounter_set_types_project_code" not in _unique_names(conn, "encounter_set_types"):
            op.create_unique_constraint("uq_encounter_set_types_project_code", "encounter_set_types", ["project_id", "code"])

    _create_index_if_missing(conn, "ix_encounter_set_types_project_id", "encounter_set_types", ["project_id"])
    _create_index_if_missing(conn, "ix_encounter_set_types_active", "encounter_set_types", ["active"])
    _create_index_if_missing(conn, "ix_encounter_set_types_project_active", "encounter_set_types", ["project_id", "active"])
    _create_index_if_missing(conn, "ix_encounter_set_types_target_scheme_id", "encounter_set_types", ["target_scheme_id"])
    _create_index_if_missing(conn, "ix_encounter_set_types_created_by_user_id", "encounter_set_types", ["created_by_user_id"])
    _create_index_if_missing(conn, "ix_encounter_set_types_updated_by_user_id", "encounter_set_types", ["updated_by_user_id"])


def downgrade() -> None:
    conn = op.get_bind()
    if "encounter_set_types" not in _table_names(conn):
        return
    op.drop_table("encounter_set_types")
