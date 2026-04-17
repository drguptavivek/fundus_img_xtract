"""add mobile auth sessions

Revision ID: 7c1e9bd12f44
Revises: 6f4b2d1c9a7e
Create Date: 2026-03-20 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c1e9bd12f44"
down_revision: Union[str, Sequence[str], None] = "6f4b2d1c9a7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "mobile_auth_sessions" not in inspector.get_table_names():
        op.create_table(
            "mobile_auth_sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("device_name", sa.String(length=255), nullable=False),
            sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
            sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_ip", sa.String(length=64), nullable=True),
            sa.Column("last_user_agent", sa.String(length=512), nullable=True),
            sa.Column("allowed_lab_unit_ids", sa.Text(), nullable=True),
            sa.Column("allowed_disease_ids", sa.Text(), nullable=True),
            sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_by_session_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["replaced_by_session_id"], ["mobile_auth_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("refresh_token_hash", name="uq_mobile_auth_sessions_refresh_hash"),
            sa.UniqueConstraint("user_id", "device_id", name="uq_mobile_auth_sessions_user_device"),
        )

    inspector = sa.inspect(conn)
    indexes = {index["name"] for index in inspector.get_indexes("mobile_auth_sessions")}
    if "ix_mobile_auth_sessions_user_id" not in indexes:
        op.create_index("ix_mobile_auth_sessions_user_id", "mobile_auth_sessions", ["user_id"])
    if "ix_mobile_auth_sessions_refresh_token_hash" not in indexes:
        op.create_index("ix_mobile_auth_sessions_refresh_token_hash", "mobile_auth_sessions", ["refresh_token_hash"], unique=True)
    if "ix_mobile_auth_sessions_refresh_token_expires_at" not in indexes:
        op.create_index("ix_mobile_auth_sessions_refresh_token_expires_at", "mobile_auth_sessions", ["refresh_token_expires_at"])
    if "ix_mobile_auth_sessions_is_revoked" not in indexes:
        op.create_index("ix_mobile_auth_sessions_is_revoked", "mobile_auth_sessions", ["is_revoked"])
    if "ix_mobile_auth_sessions_user_device_revoked" not in indexes:
        op.create_index(
            "ix_mobile_auth_sessions_user_device_revoked",
            "mobile_auth_sessions",
            ["user_id", "device_id", "is_revoked"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "mobile_auth_sessions" not in inspector.get_table_names():
        return

    indexes = {index["name"] for index in inspector.get_indexes("mobile_auth_sessions")}
    for index_name in [
        "ix_mobile_auth_sessions_user_device_revoked",
        "ix_mobile_auth_sessions_is_revoked",
        "ix_mobile_auth_sessions_refresh_token_expires_at",
        "ix_mobile_auth_sessions_refresh_token_hash",
        "ix_mobile_auth_sessions_user_id",
    ]:
        if index_name in indexes:
            op.drop_index(index_name, table_name="mobile_auth_sessions")

    op.drop_table("mobile_auth_sessions")
