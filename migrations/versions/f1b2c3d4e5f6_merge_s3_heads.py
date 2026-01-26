"""Merge heads for S3 config changes.

Revision ID: f1b2c3d4e5f6
Revises: 479741688eba, f0c1d2e3a4b5
Create Date: 2026-01-26
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f1b2c3d4e5f6"
down_revision = ("479741688eba", "f0c1d2e3a4b5")
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT 1")


def downgrade():
    op.execute("SELECT 1")
