"""add project verification tags

Revision ID: 900fc1af1ed3
Revises: 90059e4f7ba5
Create Date: 2026-08-31 12:44:23.185629
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "900fc1af1ed3"
down_revision: Union[str, Sequence[str], None] = "90059e4f7ba5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "verification_tags_json" not in {
        column["name"] for column in inspector.get_columns("projects")
    }:
        op.add_column(
            "projects",
            sa.Column(
                "verification_tags_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "verification_tags_json" in {
        column["name"] for column in inspector.get_columns("projects")
    }:
        op.drop_column("projects", "verification_tags_json")
