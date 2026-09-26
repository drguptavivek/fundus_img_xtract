"""Add project_sync_grants for approved desktop project data sync.

Revision ID: a1c3e5f7b9d2
Revises: f84c2d91a6b3
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a1c3e5f7b9d2"
down_revision = "f84c2d91a6b3"
branch_labels = None
depends_on = None

TABLE = "project_sync_grants"


def _has_table() -> bool:
    return TABLE in inspect(op.get_bind()).get_table_names()


def _index_names() -> set[str]:
    return {index["name"] for index in inspect(op.get_bind()).get_indexes(TABLE)}


def upgrade() -> None:
    if not _has_table():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("include_pii", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("purpose", sa.Text(), nullable=False),
            sa.Column("email_token_hash", sa.String(64), nullable=True),
            sa.Column("email_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("email_confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("credential_hash", sa.String(64), nullable=True),
            sa.Column("credential_prefix", sa.String(16), nullable=True),
            sa.Column("credential_issued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_ip", sa.String(45), nullable=True),
            sa.Column("revoked_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoke_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("uuid", name="uq_project_sync_grants_uuid"),
            sa.UniqueConstraint("email_token_hash", name="uq_project_sync_grants_email_token_hash"),
            sa.UniqueConstraint("credential_hash", name="uq_project_sync_grants_credential_hash"),
            sa.CheckConstraint(
                "status IN ('pending_email','pending_approval','approved','rejected','revoked','cancelled')",
                name="ck_project_sync_grants_status",
            ),
        )
    existing = _index_names()
    if "ix_project_sync_grants_project_id" not in existing:
        op.create_index("ix_project_sync_grants_project_id", TABLE, ["project_id"])
    if "ix_project_sync_grants_user_id" not in existing:
        op.create_index("ix_project_sync_grants_user_id", TABLE, ["user_id"])
    if "ix_project_sync_grants_status" not in existing:
        op.create_index("ix_project_sync_grants_status", TABLE, ["status"])
    if "uq_project_sync_grants_open" not in existing:
        op.create_index(
            "uq_project_sync_grants_open",
            TABLE,
            ["project_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('pending_email','pending_approval','approved')"),
        )


def downgrade() -> None:
    if not _has_table():
        return
    existing = _index_names()
    for name in (
        "uq_project_sync_grants_open",
        "ix_project_sync_grants_status",
        "ix_project_sync_grants_user_id",
        "ix_project_sync_grants_project_id",
    ):
        if name in existing:
            op.drop_index(name, table_name=TABLE)
    op.drop_table(TABLE)
