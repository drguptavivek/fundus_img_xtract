"""add amd reports

Revision ID: a1b2c3d4e5f7
Revises: f3a5c7d9e1b2
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a1b2c3d4e5f7"
down_revision = "f3a5c7d9e1b2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("amd_reports"):
        op.create_table(
            "amd_reports",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("patient_encounter_id", sa.Integer(), nullable=False),
            sa.Column("uuid", sa.String(length=36), nullable=True),
            sa.Column("result", sa.String(), nullable=True),
            sa.Column("qualitative_result", sa.String(), nullable=True),
            sa.Column("report_file_name", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["patient_encounter_id"], ["patient_encounters.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = {idx["name"] for idx in inspect(bind).get_indexes("amd_reports")}
    if "ix_amd_reports_patient_encounter_id" not in indexes:
        op.create_index("ix_amd_reports_patient_encounter_id", "amd_reports", ["patient_encounter_id"])
    if "ix_amd_reports_uuid" not in indexes:
        op.create_index("ix_amd_reports_uuid", "amd_reports", ["uuid"], unique=True)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("amd_reports"):
        indexes = {idx["name"] for idx in inspector.get_indexes("amd_reports")}
        if "ix_amd_reports_uuid" in indexes:
            op.drop_index("ix_amd_reports_uuid", table_name="amd_reports")
        if "ix_amd_reports_patient_encounter_id" in indexes:
            op.drop_index("ix_amd_reports_patient_encounter_id", table_name="amd_reports")
        op.drop_table("amd_reports")
