"""Add centering to encounter_files

Revision ID: 7e6d9c9b4d6d
Revises: d7e3fb45da1d
Create Date: 2026-02-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7e6d9c9b4d6d"
down_revision: Union[str, Sequence[str], None] = "d7e3fb45da1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {column["name"] for column in inspector.get_columns("encounter_files")}

    if "centering" not in columns:
        op.add_column(
            "encounter_files",
            sa.Column("centering", sa.String(length=16), nullable=True),
        )

    if not op.get_context().dialect.has_index(conn, "encounter_files", op.f("ix_encounter_files_centering")):
        op.create_index(
            op.f("ix_encounter_files_centering"),
            "encounter_files",
            ["centering"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_encounter_files_centering"), table_name="encounter_files")
    op.drop_column("encounter_files", "centering")
