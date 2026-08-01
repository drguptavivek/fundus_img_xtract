"""Add project manual remote inference workflows.

Revision ID: d8e9f0a1b2c3
Revises: b6c7d8e9f0a1
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa


revision = "d8e9f0a1b2c3"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


TABLE_NAME = "project_manual_remote_inference_workflows"


def _index_names(conn) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(TABLE_NAME)}


def upgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in sa.inspect(conn).get_table_names():
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("upload_kind", sa.String(length=32), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint(
                "project_id",
                "disease_id",
                "ai_model_id",
                "upload_kind",
                name="uq_project_manual_remote_inference_workflow",
            ),
            sa.CheckConstraint(
                "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')",
                name="ck_project_manual_remote_inference_upload_kind",
            ),
        )
    indexes = _index_names(conn)
    for column_name in ("project_id", "disease_id", "ai_model_id", "upload_kind", "active"):
        index_name = f"ix_project_manual_remote_inference_workflows_{column_name}"
        if index_name not in indexes:
            op.create_index(index_name, TABLE_NAME, [column_name])
            indexes.add(index_name)
    if "ix_project_manual_remote_inference_project_active" not in indexes:
        op.create_index(
            "ix_project_manual_remote_inference_project_active",
            TABLE_NAME,
            ["project_id", "active"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME in sa.inspect(conn).get_table_names():
        op.drop_table(TABLE_NAME)
