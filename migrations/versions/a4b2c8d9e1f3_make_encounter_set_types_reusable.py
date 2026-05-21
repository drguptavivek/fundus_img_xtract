"""make encounter set types reusable

Revision ID: a4b2c8d9e1f3
Revises: f9c8e7d6a5b4
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a4b2c8d9e1f3"
down_revision: Union[str, Sequence[str], None] = "f9c8e7d6a5b4"
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
    if table_name in _table_names(conn) and not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def _drop_index_if_exists(conn, name: str, table_name: str) -> None:
    if table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if "upload_metadata_field_definitions" not in tables:
        op.create_table(
            "upload_metadata_field_definitions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("label", sa.String(length=150), nullable=False),
            sa.Column("field_type", sa.String(length=32), nullable=False),
            sa.Column("selection_mode", sa.String(length=16), nullable=True),
            sa.Column("options_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("required_at_upload_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("required_for_verification_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("visible_to_grader_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_pii_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_upload_metadata_field_definitions_created_by", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], name="fk_upload_metadata_field_definitions_updated_by", ondelete="SET NULL"),
            sa.UniqueConstraint("scope", "key", name="uq_upload_metadata_field_definitions_scope_key"),
        )
    _create_index_if_missing(conn, "ix_upload_metadata_field_definitions_scope", "upload_metadata_field_definitions", ["scope"])
    _create_index_if_missing(conn, "ix_upload_metadata_field_definitions_active", "upload_metadata_field_definitions", ["active"])
    _create_index_if_missing(conn, "ix_upload_metadata_field_definitions_created_by_user_id", "upload_metadata_field_definitions", ["created_by_user_id"])
    _create_index_if_missing(conn, "ix_upload_metadata_field_definitions_updated_by_user_id", "upload_metadata_field_definitions", ["updated_by_user_id"])
    _create_index_if_missing(conn, "ix_upload_metadata_field_definitions_scope_active", "upload_metadata_field_definitions", ["scope", "active"])

    if "encounter_set_types" not in tables:
        return

    columns = _column_names(conn, "encounter_set_types")
    if "project_id" in columns:
        op.execute(
            """
            WITH ranked AS (
                SELECT id, code, row_number() OVER (PARTITION BY code ORDER BY id) AS rn
                FROM encounter_set_types
            )
            UPDATE encounter_set_types AS est
            SET code = ranked.code || '_' || est.id::text
            FROM ranked
            WHERE est.id = ranked.id AND ranked.rn > 1
            """
        )
        if "uq_encounter_set_types_project_code" in _unique_names(conn, "encounter_set_types"):
            op.drop_constraint("uq_encounter_set_types_project_code", "encounter_set_types", type_="unique")
        if "fk_encounter_set_types_project_id_projects" in _fk_names(conn, "encounter_set_types"):
            op.drop_constraint("fk_encounter_set_types_project_id_projects", "encounter_set_types", type_="foreignkey")
        _drop_index_if_exists(conn, "ix_encounter_set_types_project_active", "encounter_set_types")
        _drop_index_if_exists(conn, "ix_encounter_set_types_project_id", "encounter_set_types")
        op.drop_column("encounter_set_types", "project_id")
    if "uq_encounter_set_types_code" not in _unique_names(conn, "encounter_set_types"):
        op.create_unique_constraint("uq_encounter_set_types_code", "encounter_set_types", ["code"])


def downgrade() -> None:
    conn = op.get_bind()
    if "encounter_set_types" in _table_names(conn):
        if "uq_encounter_set_types_code" in _unique_names(conn, "encounter_set_types"):
            op.drop_constraint("uq_encounter_set_types_code", "encounter_set_types", type_="unique")
        if "project_id" not in _column_names(conn, "encounter_set_types"):
            op.add_column("encounter_set_types", sa.Column("project_id", sa.Integer(), nullable=True))
        if "fk_encounter_set_types_project_id_projects" not in _fk_names(conn, "encounter_set_types"):
            op.create_foreign_key("fk_encounter_set_types_project_id_projects", "encounter_set_types", "projects", ["project_id"], ["id"], ondelete="CASCADE")
        if "uq_encounter_set_types_project_code" not in _unique_names(conn, "encounter_set_types"):
            op.create_unique_constraint("uq_encounter_set_types_project_code", "encounter_set_types", ["project_id", "code"])
        _create_index_if_missing(conn, "ix_encounter_set_types_project_id", "encounter_set_types", ["project_id"])
        _create_index_if_missing(conn, "ix_encounter_set_types_project_active", "encounter_set_types", ["project_id", "active"])

    if "upload_metadata_field_definitions" in _table_names(conn):
        op.drop_table("upload_metadata_field_definitions")
