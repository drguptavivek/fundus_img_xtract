"""add_hospital_isolation_to_users_fix

Revision ID: 1517278bfc85
Revises: 7399d7a901ce
Create Date: 2026-01-14 04:54:45.353407

Adds hospital_id and is_master_admin columns to users table for hospital isolation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1517278bfc85'
down_revision: Union[str, Sequence[str], None] = '7399d7a901ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add hospital isolation columns to users table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {column["name"] for column in inspector.get_columns("users")}

    if "is_master_admin" not in columns:
        # Add is_master_admin column first (no FK)
        op.add_column(
            "users",
            sa.Column(
                "is_master_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    if "hospital_id" not in columns:
        # Add hospital_id column with FK to hospitals table
        op.add_column(
            "users",
            sa.Column(
                "hospital_id",
                sa.Integer(),
                nullable=True,
            ),
        )

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("users")}
    if "fk_users_hospital_id" not in foreign_keys:
        op.create_foreign_key(
            "fk_users_hospital_id",
            "users",
            "hospitals",
            ["hospital_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    if not op.get_context().dialect.has_index(conn, "users", "ix_users_hospital_id"):
        op.create_index(
            "ix_users_hospital_id",
            "users",
            ["hospital_id"],
        )


def downgrade() -> None:
    """Downgrade schema: Remove hospital isolation columns from users table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {column["name"] for column in inspector.get_columns("users")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("users")}

    if op.get_context().dialect.has_index(conn, "users", "ix_users_hospital_id"):
        op.drop_index("ix_users_hospital_id", table_name="users")

    if "fk_users_hospital_id" in foreign_keys:
        op.drop_constraint("fk_users_hospital_id", "users", type_="foreignkey")

    if "hospital_id" in columns:
        op.drop_column("users", "hospital_id")

    if "is_master_admin" in columns:
        op.drop_column("users", "is_master_admin")
