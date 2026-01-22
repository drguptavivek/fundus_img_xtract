"""add_pii_verification

Revision ID: 2b691dfc8c46
Revises: a8599e75315b
Create Date: 2026-01-22 03:52:03.306601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '2b691dfc8c46'
down_revision: Union[str, Sequence[str], None] = 'a8599e75315b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    if "image_pii_verifications" not in inspector.get_table_names():
        op.create_table(
            "image_pii_verifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("image_uuid", sa.String(length=36), nullable=False),
            sa.Column("image_variant", sa.String(length=8), nullable=False),
            sa.Column("pii_status", sa.String(length=16), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("image_variant IN ('orig', 'edited')", name="ck_pii_verification_variant"),
            sa.CheckConstraint("pii_status IN ('detected', 'clear', 'error')", name="ck_pii_verification_status"),
            sa.UniqueConstraint("image_uuid", "image_variant", name="uq_image_pii_verification_uuid_variant"),
        )
    if not op.get_context().dialect.has_index(conn, "image_pii_verifications", "ix_image_pii_verifications_image_uuid"):
        op.create_index("ix_image_pii_verifications_image_uuid", "image_pii_verifications", ["image_uuid"], unique=False)
    if not op.get_context().dialect.has_index(conn, "image_pii_verifications", "ix_image_pii_verifications_image_variant"):
        op.create_index("ix_image_pii_verifications_image_variant", "image_pii_verifications", ["image_variant"], unique=False)
    if not op.get_context().dialect.has_index(conn, "image_pii_verifications", "ix_image_pii_verifications_pii_status"):
        op.create_index("ix_image_pii_verifications_pii_status", "image_pii_verifications", ["pii_status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    if "image_pii_verifications" in inspector.get_table_names():
        if op.get_context().dialect.has_index(conn, "image_pii_verifications", "ix_image_pii_verifications_pii_status"):
            op.drop_index("ix_image_pii_verifications_pii_status", table_name="image_pii_verifications")
        if op.get_context().dialect.has_index(conn, "image_pii_verifications", "ix_image_pii_verifications_image_variant"):
            op.drop_index("ix_image_pii_verifications_image_variant", table_name="image_pii_verifications")
        if op.get_context().dialect.has_index(conn, "image_pii_verifications", "ix_image_pii_verifications_image_uuid"):
            op.drop_index("ix_image_pii_verifications_image_uuid", table_name="image_pii_verifications")
        op.drop_table("image_pii_verifications")
