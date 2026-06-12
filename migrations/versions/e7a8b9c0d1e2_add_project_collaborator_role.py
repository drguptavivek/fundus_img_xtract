"""add project collaborator role

Revision ID: e7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-12 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


ROLE_CHECK_NAME = "ck_project_investigator_role"
OLD_ROLE_CHECK = "role IN ('principal_investigator','co_investigator','coordinator')"
NEW_ROLE_CHECK = "role IN ('principal_investigator','co_investigator','coordinator','collaborator')"


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspector.get_check_constraints(table_name)
    )


def _role_exists(conn, role_name: str) -> bool:
    return bool(conn.execute(sa.text("SELECT 1 FROM roles WHERE name = :name"), {"name": role_name}).first())


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "roles" in inspector.get_table_names() and not _role_exists(conn, "collaborator"):
        conn.execute(sa.text("INSERT INTO roles (name) VALUES (:name)"), {"name": "collaborator"})

    if "project_investigators" not in inspector.get_table_names():
        return

    if _constraint_exists(conn, "project_investigators", ROLE_CHECK_NAME):
        op.drop_constraint(ROLE_CHECK_NAME, "project_investigators", type_="check")
    op.create_check_constraint(ROLE_CHECK_NAME, "project_investigators", NEW_ROLE_CHECK)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "project_investigators" in inspector.get_table_names():
        conn.execute(sa.text("DELETE FROM project_investigators WHERE role = :role"), {"role": "collaborator"})
        if _constraint_exists(conn, "project_investigators", ROLE_CHECK_NAME):
            op.drop_constraint(ROLE_CHECK_NAME, "project_investigators", type_="check")
        op.create_check_constraint(ROLE_CHECK_NAME, "project_investigators", OLD_ROLE_CHECK)

    if "roles" in inspector.get_table_names():
        conn.execute(
            sa.text(
                "DELETE FROM roles WHERE name = :name AND NOT EXISTS ("
                "SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.name = :name"
                ") AND NOT EXISTS ("
                "SELECT 1 FROM project_investigators WHERE role = :name"
                ")"
            ),
            {"name": "collaborator"},
        )
