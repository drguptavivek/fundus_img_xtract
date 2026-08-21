"""Add mobile device enrolment gate, session revoke reason, and field roles.

Revision ID: b1c2d3e4f5a6
Revises: 66042c5dfc7f
Create Date: 2026-08-21

Every existing (user_id, device_id) pair is backfilled as an approved personal
device so current uploaders keep working the moment this deploys; without that
backfill the new login gate would lock out the entire installed base.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "66042c5dfc7f"
branch_labels = None
depends_on = None

FIELD_ROLES = ("field_optometrist", "field_ophthalmologist")


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind, table: str, column: str) -> bool:
    if not _has_table(bind, table):
        return False
    return column in {col["name"] for col in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "mobile_devices"):
        op.create_table(
            "mobile_devices",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("device_id", sa.String(length=128), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
            sa.Column("device_kind", sa.String(length=16), server_default="personal", nullable=False),
            sa.Column("platform", sa.String(length=16), nullable=True),
            sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("enrolled_by_user_id", sa.Integer(), nullable=True),
            sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["enrolled_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "device_id", name="uq_mobile_devices_user_device"),
            sa.CheckConstraint("status IN ('pending','approved','blocked')", name="ck_mobile_devices_status"),
            sa.CheckConstraint("device_kind IN ('personal','shared')", name="ck_mobile_devices_kind"),
            sa.CheckConstraint(
                "platform IS NULL OR platform IN ('android','ios','windows','macos','web')",
                name="ck_mobile_devices_platform",
            ),
        )
        op.create_index("ix_mobile_devices_user_id", "mobile_devices", ["user_id"])
        op.create_index("ix_mobile_devices_status", "mobile_devices", ["status"])
        op.create_index("ix_mobile_devices_user_status", "mobile_devices", ["user_id", "status"])

    if not _has_table(bind, "mobile_device_enrolment_codes"):
        op.create_table(
            "mobile_device_enrolment_codes",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("device_kind", sa.String(length=16), server_default="personal", nullable=False),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("issued_by_user_id", sa.Integer(), nullable=True),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("used_device_id", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code_hash", name="uq_mobile_device_codes_hash"),
            sa.CheckConstraint("device_kind IN ('personal','shared')", name="ck_mobile_device_codes_kind"),
        )
        op.create_index("ix_mobile_device_codes_user_id", "mobile_device_enrolment_codes", ["user_id"])
        op.create_index("ix_mobile_device_codes_expires_at", "mobile_device_enrolment_codes", ["expires_at"])
        op.create_index("ix_mobile_device_codes_hash", "mobile_device_enrolment_codes", ["code_hash"])
        op.create_index(
            "ix_mobile_device_codes_user_used", "mobile_device_enrolment_codes", ["user_id", "used_at"]
        )

    if not _has_column(bind, "mobile_auth_sessions", "revoked_reason"):
        op.add_column(
            "mobile_auth_sessions",
            sa.Column("revoked_reason", sa.String(length=32), nullable=True),
        )

    # Grandfather every device that already has a session, so the new gate does
    # not lock out existing users on deploy.
    if _has_table(bind, "mobile_auth_sessions"):
        op.execute(
            sa.text(
                """
                INSERT INTO mobile_devices (
                    user_id, device_id, label, status, device_kind,
                    enrolled_at, created_at, updated_at
                )
                SELECT DISTINCT ON (s.user_id, s.device_id)
                    s.user_id, s.device_id, s.device_name, 'approved', 'personal',
                    NOW(), NOW(), NOW()
                FROM mobile_auth_sessions s
                ORDER BY s.user_id, s.device_id, s.created_at DESC
                ON CONFLICT (user_id, device_id) DO NOTHING
                """
            )
        )

    for role_name in FIELD_ROLES:
        op.execute(
            sa.text(
                "INSERT INTO roles (name) SELECT :name "
                "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = :name)"
            ).bindparams(name=role_name)
        )


def downgrade() -> None:
    bind = op.get_bind()

    for role_name in FIELD_ROLES:
        # Drop grants first so the role delete cannot fail on a dangling FK.
        if _has_table(bind, "user_roles"):
            op.execute(
                sa.text(
                    "DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE name = :name)"
                ).bindparams(name=role_name)
            )
        if _has_table(bind, "project_role_grants"):
            op.execute(
                sa.text(
                    "DELETE FROM project_role_grants WHERE role_id IN "
                    "(SELECT id FROM roles WHERE name = :name)"
                ).bindparams(name=role_name)
            )
        op.execute(sa.text("DELETE FROM roles WHERE name = :name").bindparams(name=role_name))

    if _has_column(bind, "mobile_auth_sessions", "revoked_reason"):
        op.drop_column("mobile_auth_sessions", "revoked_reason")

    if _has_table(bind, "mobile_device_enrolment_codes"):
        op.drop_table("mobile_device_enrolment_codes")

    if _has_table(bind, "mobile_devices"):
        op.drop_table("mobile_devices")
