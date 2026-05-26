"""add remidio api routing profiles

Revision ID: a1b2c3d4e5f8
Revises: 9b7e6a5d4c3f
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, Sequence[str], None] = "9b7e6a5d4c3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROUTING_PROFILES = "remidio_api_routing_profiles"
BINDINGS = "project_upload_profile_remidio_api_bindings"


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _index_exists(conn, table_name: str, name: str) -> bool:
    return table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name)


def _constraint_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    inspector = inspect(conn)
    names = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
    names.update(constraint["name"] for constraint in inspector.get_foreign_keys(table_name))
    return names


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if ROUTING_PROFILES not in tables:
        op.create_table(
            ROUTING_PROFILES,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_remidio_api_routing_profile_project", ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", "name", name="uq_remidio_api_routing_profile_project_name"),
        )
    if not _index_exists(conn, ROUTING_PROFILES, "ix_remidio_api_routing_profiles_project_id"):
        op.create_index("ix_remidio_api_routing_profiles_project_id", ROUTING_PROFILES, ["project_id"])
    if not _index_exists(conn, ROUTING_PROFILES, "ix_remidio_api_routing_profiles_active"):
        op.create_index("ix_remidio_api_routing_profiles_active", ROUTING_PROFILES, ["active"])
    if not _index_exists(conn, ROUTING_PROFILES, "ix_remidio_api_routing_profiles_project_active"):
        op.create_index("ix_remidio_api_routing_profiles_project_active", ROUTING_PROFILES, ["project_id", "active"])

    if BINDINGS in tables and "routing_profile_id" not in _column_names(conn, BINDINGS):
        op.add_column(BINDINGS, sa.Column("routing_profile_id", sa.Integer(), nullable=True))
    if BINDINGS in _table_names(conn) and ROUTING_PROFILES in _table_names(conn):
        if "fk_pup_remidio_api_binding_routing_profile" not in _constraint_names(conn, BINDINGS):
            op.create_foreign_key(
                "fk_pup_remidio_api_binding_routing_profile",
                BINDINGS,
                ROUTING_PROFILES,
                ["routing_profile_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_route_profile"):
            op.create_index(
                "ix_pup_remidio_api_binding_route_profile",
                BINDINGS,
                ["routing_profile_id"],
            )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if BINDINGS in tables and "routing_profile_id" in _column_names(conn, BINDINGS):
        if _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_route_profile"):
            op.drop_index("ix_pup_remidio_api_binding_route_profile", table_name=BINDINGS)
        if "fk_pup_remidio_api_binding_routing_profile" in _constraint_names(conn, BINDINGS):
            op.drop_constraint("fk_pup_remidio_api_binding_routing_profile", BINDINGS, type_="foreignkey")
        op.drop_column(BINDINGS, "routing_profile_id")

    if ROUTING_PROFILES in _table_names(conn):
        if _index_exists(conn, ROUTING_PROFILES, "ix_remidio_api_routing_profiles_project_active"):
            op.drop_index("ix_remidio_api_routing_profiles_project_active", table_name=ROUTING_PROFILES)
        if _index_exists(conn, ROUTING_PROFILES, "ix_remidio_api_routing_profiles_active"):
            op.drop_index("ix_remidio_api_routing_profiles_active", table_name=ROUTING_PROFILES)
        if _index_exists(conn, ROUTING_PROFILES, "ix_remidio_api_routing_profiles_project_id"):
            op.drop_index("ix_remidio_api_routing_profiles_project_id", table_name=ROUTING_PROFILES)
        op.drop_table(ROUTING_PROFILES)
