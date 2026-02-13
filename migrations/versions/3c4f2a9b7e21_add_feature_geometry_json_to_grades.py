"""add feature geometry json to grades

Revision ID: 3c4f2a9b7e21
Revises: 8d98ff8821fd
Create Date: 2026-02-13 10:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3c4f2a9b7e21"
down_revision = "8d98ff8821fd"
branch_labels = None
depends_on = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _column_exists(inspector, "grades", "feature_geometry_json"):
        op.add_column(
            "grades",
            sa.Column("feature_geometry_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )

    if not _column_exists(inspector, "intra_rater_grades", "feature_geometry_json"):
        op.add_column(
            "intra_rater_grades",
            sa.Column("feature_geometry_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if _column_exists(inspector, "intra_rater_grades", "feature_geometry_json"):
        op.drop_column("intra_rater_grades", "feature_geometry_json")

    if _column_exists(inspector, "grades", "feature_geometry_json"):
        op.drop_column("grades", "feature_geometry_json")
