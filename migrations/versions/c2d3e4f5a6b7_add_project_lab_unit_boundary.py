"""Add explicit project Lab Unit boundary.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-22

Existing projects are linked to every Lab Unit that exists at migration time.
This preserves their prior unconstrained behavior until a System Admin narrows
the new explicit configuration. New projects start with no Lab Units.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _index_names(bind, table: str) -> set[str]:
    if not _has_table(bind, table):
        return set()
    return {row["name"] for row in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "project_lab_units"):
        op.create_table(
            "project_lab_units",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "lab_unit_id", name="uq_project_lab_units_project_lab"),
        )
    indexes = _index_names(bind, "project_lab_units")
    if "ix_project_lab_units_project_id" not in indexes:
        op.create_index("ix_project_lab_units_project_id", "project_lab_units", ["project_id"])
    if "ix_project_lab_units_lab_unit_id" not in indexes:
        op.create_index("ix_project_lab_units_lab_unit_id", "project_lab_units", ["lab_unit_id"])
    if "ix_project_lab_units_active" not in indexes:
        op.create_index("ix_project_lab_units_active", "project_lab_units", ["active"])
    if "ix_project_lab_units_project_active" not in indexes:
        op.create_index("ix_project_lab_units_project_active", "project_lab_units", ["project_id", "active"])

    # Prior to this table, every project could reference every Lab Unit. Preserve
    # that behavior for existing projects; System Admin can explicitly narrow it.
    bind.execute(sa.text("""
        INSERT INTO project_lab_units (project_id, lab_unit_id, active, created_at, updated_at)
        SELECT project.id, lab.id, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM projects AS project
        CROSS JOIN lab_units AS lab
        ON CONFLICT (project_id, lab_unit_id) DO NOTHING
    """))

    # These catalog rows are shared by project and legacy/global workflows. Do
    # not remove role records during downgrade.
    if _has_table(bind, "roles"):
        bind.execute(sa.text("""
            INSERT INTO roles (name)
            VALUES ('project_admin'), ('verifier')
            ON CONFLICT (name) DO NOTHING
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "project_lab_units"):
        op.drop_table("project_lab_units")
