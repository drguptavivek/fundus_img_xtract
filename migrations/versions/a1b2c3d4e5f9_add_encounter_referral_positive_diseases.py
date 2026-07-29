"""add encounter referral positive diseases

Revision ID: a1b2c3d4e5f9
Revises: a1b2c3d4e5f7
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5f9"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("patient_encounters")}
    if "referral_positive_diseases_json" not in columns:
        op.add_column(
            "patient_encounters",
            sa.Column("referral_positive_diseases_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("patient_encounters")}
    if "referral_positive_diseases_json" in columns:
        op.drop_column("patient_encounters", "referral_positive_diseases_json")
