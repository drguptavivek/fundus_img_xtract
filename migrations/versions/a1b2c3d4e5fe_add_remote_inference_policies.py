"""Add remote inference policies.

Revision ID: a1b2c3d4e5fe
Revises: a1b2c3d4e5fd
Create Date: 2026-07-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5fe"
down_revision = "a1b2c3d4e5fd"
branch_labels = None
depends_on = None


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _create_index(conn, name: str, table_name: str, columns: list[str]) -> None:
    indexes = {index["name"] for index in sa.inspect(conn).get_indexes(table_name)}
    if name not in indexes:
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)

    if "remote_inference_policies" not in tables:
        op.create_table(
            "remote_inference_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("name", name="uq_remote_inference_policies_name"),
        )
    _create_index(conn, "ix_remote_inference_policies_active", "remote_inference_policies", ["active"])

    if "remote_inference_policy_rules" not in _tables(conn):
        op.create_table(
            "remote_inference_policy_rules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("policy_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("upload_kind", sa.String(length=32), nullable=False),
            sa.Column("trigger_timing", sa.String(length=32), nullable=False),
            sa.Column("encounter_eligibility", sa.String(length=64), nullable=False, server_default="always"),
            sa.Column("image_selection", sa.String(length=64), nullable=False, server_default="all_eligible_images"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["policy_id"], ["remote_inference_policies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("policy_id", "disease_id", "ai_model_id", "upload_kind", name="uq_remote_inference_policy_rule"),
            sa.CheckConstraint(
                "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')",
                name="ck_remote_inference_rule_upload_kind",
            ),
            sa.CheckConstraint(
                "trigger_timing IN ('on_image_received','on_report_received','after_verification','manual_only')",
                name="ck_remote_inference_rule_trigger",
            ),
            sa.CheckConstraint(
                "encounter_eligibility IN ('always','if_matching_report_present','if_matching_report_absent','if_any_report_present')",
                name="ck_remote_inference_rule_encounter_eligibility",
            ),
            sa.CheckConstraint(
                "image_selection IN ('all_eligible_images','disc_focused_images','macula_focused_images','disc_or_macula_images')",
                name="ck_remote_inference_rule_image_selection",
            ),
        )
    for column_name in ["policy_id", "disease_id", "ai_model_id", "upload_kind", "trigger_timing", "active"]:
        _create_index(conn, f"ix_remote_inference_policy_rules_{column_name}", "remote_inference_policy_rules", [column_name])
    _create_index(conn, "ix_remote_inference_rules_policy_active", "remote_inference_policy_rules", ["policy_id", "active"])

    if "disease_report_linkages" not in _tables(conn):
        op.create_table(
            "disease_report_linkages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("report_source", sa.String(length=64), nullable=False, server_default="remidio"),
            sa.Column("report_type", sa.String(length=64), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("disease_id", "report_source", "report_type", name="uq_disease_report_linkage"),
            sa.CheckConstraint("report_source IN ('remidio')", name="ck_disease_report_linkage_source"),
            sa.CheckConstraint("report_type IN ('dr','amd','glaucoma')", name="ck_disease_report_linkage_type"),
        )
    for column_name in ["disease_id", "report_type", "active"]:
        _create_index(conn, f"ix_disease_report_linkages_{column_name}", "disease_report_linkages", [column_name])
    _create_index(conn, "ix_disease_report_linkages_disease_active", "disease_report_linkages", ["disease_id", "active"])

    if "project_remote_inference_policies" not in _tables(conn):
        op.create_table(
            "project_remote_inference_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("remote_inference_policy_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["remote_inference_policy_id"], ["remote_inference_policies.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", name="uq_project_remote_inference_policy_project"),
        )
    for column_name in ["project_id", "remote_inference_policy_id", "active"]:
        _create_index(conn, f"ix_project_remote_inference_policies_{column_name}", "project_remote_inference_policies", [column_name])
    _create_index(
        conn,
        "ix_project_remote_inference_policies_project_active",
        "project_remote_inference_policies",
        ["project_id", "active"],
    )

    op.execute(
        """
        INSERT INTO disease_report_linkages (disease_id, report_source, report_type, active, created_at, updated_at)
        SELECT id, 'remidio', remidio_ocr_linkage, true, NOW(), NOW()
        FROM diseases
        WHERE remidio_ocr_linkage IN ('dr', 'amd', 'glaucoma')
        ON CONFLICT (disease_id, report_source, report_type)
        DO UPDATE SET active = true, updated_at = NOW()
        """
    )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    for table_name in [
        "project_remote_inference_policies",
        "disease_report_linkages",
        "remote_inference_policy_rules",
        "remote_inference_policies",
    ]:
        if table_name in tables:
            op.drop_table(table_name)
