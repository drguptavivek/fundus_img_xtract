"""add metadata backfill modes

Revision ID: 8d0f6a3c2b11
Revises: 7b3c2f9d4e1a
Create Date: 2026-01-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "8d0f6a3c2b11"
down_revision: Union[str, Sequence[str], None] = "7b3c2f9d4e1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("image_metadata_backfill_jobs")}

    if "run_metadata" not in columns:
        op.add_column(
            "image_metadata_backfill_jobs",
            sa.Column("run_metadata", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
    if "run_pii" not in columns:
        op.add_column(
            "image_metadata_backfill_jobs",
            sa.Column("run_pii", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    op.execute(
        "UPDATE image_metadata_backfill_jobs SET run_metadata = true WHERE run_metadata IS NULL"
    )
    op.execute(
        "UPDATE image_metadata_backfill_jobs SET run_pii = true WHERE run_pii IS NULL"
    )

    with op.batch_alter_table("image_metadata_backfill_jobs") as batch_op:
        batch_op.alter_column("run_metadata", server_default=None)
        batch_op.alter_column("run_pii", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("image_metadata_backfill_jobs")}

    with op.batch_alter_table("image_metadata_backfill_jobs") as batch_op:
        if "run_pii" in columns:
            batch_op.drop_column("run_pii")
        if "run_metadata" in columns:
            batch_op.drop_column("run_metadata")
