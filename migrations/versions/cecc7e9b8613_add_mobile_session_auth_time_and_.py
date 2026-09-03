"""add mobile session auth time and passkeys

Revision ID: cecc7e9b8613
Revises: 91a4c6e8f2b0
Create Date: 2026-09-03 01:08:43.593929

Mobile sessions record when the user last proved their identity
(``last_authenticated_at``: login or re-authentication, not refresh) so the
grader can require re-authentication after inactivity. ``mobile_passkeys``
stores WebAuthn credentials used as the biometric re-authentication method.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cecc7e9b8613'
down_revision: Union[str, Sequence[str], None] = '91a4c6e8f2b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return any(col["name"] == column for col in _inspector().get_columns(table))


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_index(table: str, name: str) -> bool:
    return any(index["name"] == name for index in _inspector().get_indexes(table))


def upgrade() -> None:
    """Upgrade schema."""
    if _has_table("mobile_auth_sessions") and not _has_column("mobile_auth_sessions", "last_authenticated_at"):
        op.add_column(
            "mobile_auth_sessions",
            sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        )
        # Existing sessions proved identity at creation (login).
        op.execute("UPDATE mobile_auth_sessions SET last_authenticated_at = created_at WHERE last_authenticated_at IS NULL")

    if not _has_table("mobile_passkeys"):
        op.create_table(
            "mobile_passkeys",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("credential_id", sa.String(1024), nullable=False),
            sa.Column("public_key", sa.LargeBinary(), nullable=False),
            sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("aaguid", sa.String(64), nullable=True),
            sa.Column("transports", sa.String(255), nullable=True),
            sa.Column("label", sa.String(255), nullable=True),
            sa.Column("device_id", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("credential_id", name="uq_mobile_passkeys_credential_id"),
        )
    if _has_table("mobile_passkeys") and not _has_index("mobile_passkeys", "ix_mobile_passkeys_user_id"):
        op.create_index("ix_mobile_passkeys_user_id", "mobile_passkeys", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    if _has_table("mobile_passkeys"):
        if _has_index("mobile_passkeys", "ix_mobile_passkeys_user_id"):
            op.drop_index("ix_mobile_passkeys_user_id", table_name="mobile_passkeys")
        op.drop_table("mobile_passkeys")
    if _has_table("mobile_auth_sessions") and _has_column("mobile_auth_sessions", "last_authenticated_at"):
        op.drop_column("mobile_auth_sessions", "last_authenticated_at")
