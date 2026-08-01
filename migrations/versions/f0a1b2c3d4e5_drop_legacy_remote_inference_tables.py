"""Drop retired remote inference configuration tables.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


LEGACY_TABLES = (
    "project_remote_inference_policies",
    "remote_inference_policy_rules",
    "remote_inference_policies",
    "upload_profile_ai_workflows",
)


def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    for table_name in LEGACY_TABLES:
        if table_name in tables:
            op.drop_table(table_name)


def downgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "remote_inference_policies" not in tables:
        op.create_table(
            "remote_inference_policies",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        op.create_index("ix_remote_inference_policies_active", "remote_inference_policies", ["active"])
    if "remote_inference_policy_rules" not in tables:
        op.create_table(
            "remote_inference_policy_rules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("policy_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("upload_kind", sa.String(length=32), nullable=False),
            sa.Column("trigger_timing", sa.String(length=32), nullable=False),
            sa.Column("encounter_eligibility", sa.String(length=64), server_default="always", nullable=False),
            sa.Column("image_selection", sa.String(length=64), server_default="all_eligible_images", nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["policy_id"], ["remote_inference_policies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="RESTRICT"),
            sa.CheckConstraint("upload_kind IN ('direct_image','pregraded','remidio','encounter_set')", name="ck_remote_inference_rule_upload_kind"),
            sa.CheckConstraint("trigger_timing IN ('on_image_received','on_report_received','after_verification','manual_only')", name="ck_remote_inference_rule_trigger"),
            sa.CheckConstraint("encounter_eligibility IN ('always','if_matching_report_present','if_matching_report_absent','if_any_report_present')", name="ck_remote_inference_rule_encounter_eligibility"),
            sa.CheckConstraint("image_selection IN ('all_eligible_images','disc_focused_images','macula_focused_images','disc_or_macula_images')", name="ck_remote_inference_rule_image_selection"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("policy_id", "disease_id", "ai_model_id", "upload_kind", name="uq_remote_inference_policy_rule"),
        )
    if "project_remote_inference_policies" not in tables:
        op.create_table(
            "project_remote_inference_policies",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("remote_inference_policy_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["remote_inference_policy_id"], ["remote_inference_policies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", name="uq_project_remote_inference_policy_project"),
        )
    if "upload_profile_ai_workflows" not in tables:
        op.create_table(
            "upload_profile_ai_workflows",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("upload_kind", sa.String(length=32), nullable=False),
            sa.Column("auto_inference_policy", sa.String(length=64), server_default="always", nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="CASCADE"),
            sa.CheckConstraint("upload_kind IN ('direct_image','pregraded','remidio','encounter_set')", name="ck_upload_profile_ai_workflow_kind_valid"),
            sa.CheckConstraint("auto_inference_policy IN ('never','always','remidio_glaucoma_report_present')", name="ck_upload_profile_ai_workflow_auto_policy"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("upload_profile_id", "disease_id", "ai_model_id", "upload_kind", name="uq_upload_profile_ai_workflow"),
        )
