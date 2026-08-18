"""add MadhuNetrAI encounter inference

Revision ID: 6f2d8a9c1b47
Revises: 0b9488e2a0f6
Create Date: 2026-08-18 00:00:00.000000
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql


revision: str = "6f2d8a9c1b47"
down_revision: Union[str, Sequence[str], None] = "0b9488e2a0f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {row["name"] for row in inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    columns = _columns(conn, "ai_model_integrations")
    for name, column_type in (
        ("api_base_url", sa.String(1000)),
        ("environment", sa.String(32)),
        ("access_token_encrypted", sa.Text()),
        ("config_json", postgresql.JSONB()),
    ):
        if name not in columns:
            op.add_column("ai_model_integrations", sa.Column(name, column_type, nullable=True))
    op.execute("ALTER TABLE ai_model_integrations DROP CONSTRAINT IF EXISTS ck_ai_model_integration_provider_valid")
    op.create_check_constraint(
        "ck_ai_model_integration_provider_valid",
        "ai_model_integrations",
        "provider IN ('wadhwani_glaucoma','wai_dr_dme')",
    )

    if "project_encounter_ai_workflows" not in _tables(conn):
        op.create_table(
            "project_encounter_ai_workflows",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("workflow_key", sa.String(64), nullable=False, server_default="dr_dme"),
            sa.Column("automatic_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("manual_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("automatic_eligibility", sa.String(64), nullable=False, server_default="always"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("project_id", "workflow_key", name="uq_project_encounter_ai_workflow"),
            sa.CheckConstraint("workflow_key IN ('dr_dme')", name="ck_project_encounter_ai_workflow_key"),
            sa.CheckConstraint(
                "automatic_eligibility IN ('always','if_dr_ocr_report_present')",
                name="ck_project_encounter_ai_workflow_eligibility",
            ),
        )
        op.create_index("ix_project_encounter_ai_workflows_project_id", "project_encounter_ai_workflows", ["project_id"])
        op.create_index("ix_project_encounter_ai_workflows_ai_model_id", "project_encounter_ai_workflows", ["ai_model_id"])
        op.create_index("ix_project_encounter_ai_workflows_active", "project_encounter_ai_workflows", ["active"])
        op.create_index("ix_project_encounter_ai_workflow_project_active", "project_encounter_ai_workflows", ["project_id", "active"])

    if "encounter_ai_output_targets" not in _tables(conn):
        op.create_table(
            "encounter_ai_output_targets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("target_key", sa.String(64), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("label_mapping_json", postgresql.JSONB(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("ai_model_id", "target_key", name="uq_encounter_ai_output_target"),
            sa.UniqueConstraint("ai_model_id", "disease_id", name="uq_encounter_ai_output_target_disease"),
        )
        op.create_index("ix_encounter_ai_output_targets_ai_model_id", "encounter_ai_output_targets", ["ai_model_id"])
        op.create_index("ix_encounter_ai_output_targets_disease_id", "encounter_ai_output_targets", ["disease_id"])
        op.create_index("ix_encounter_ai_output_targets_active", "encounter_ai_output_targets", ["active"])

    if "encounter_ai_inference_runs" not in _tables(conn):
        op.create_table(
            "encounter_ai_inference_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("uuid", sa.String(36), nullable=False, unique=True),
            sa.Column("patient_encounter_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("integration_id", sa.Integer(), nullable=True),
            sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(32), nullable=False, server_default="automatic"),
            sa.Column("request_id", sa.String(100), nullable=False, unique=True),
            sa.Column("report_id", sa.String(128), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("request_manifest_json", postgresql.JSONB(), nullable=True),
            sa.Column("presign_response_json", postgresql.JSONB(), nullable=True),
            sa.Column("submit_response_json", postgresql.JSONB(), nullable=True),
            sa.Column("config_snapshot_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_code", sa.String(128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["patient_encounter_id"], ["patient_encounters.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["integration_id"], ["ai_model_integrations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("patient_encounter_id", "ai_model_id", name="uq_encounter_ai_run_encounter_model"),
            sa.CheckConstraint("source IN ('automatic','manual','recovery')", name="ck_encounter_ai_run_source"),
            sa.CheckConstraint(
                "status IN ('queued','presigning','uploading','submitting','success','partial','failed')",
                name="ck_encounter_ai_run_status",
            ),
        )
        for name in ("patient_encounter_id", "ai_model_id", "integration_id", "requested_by_user_id", "request_id", "report_id", "status"):
            op.create_index(f"ix_encounter_ai_inference_runs_{name}", "encounter_ai_inference_runs", [name])
        op.create_index("ix_encounter_ai_run_encounter_created", "encounter_ai_inference_runs", ["patient_encounter_id", "created_at"])

    if "encounter_ai_image_results" not in _tables(conn):
        op.create_table(
            "encounter_ai_image_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("encounter_set_image_id", sa.Integer(), nullable=False),
            sa.Column("remote_key", sa.String(1000), nullable=True),
            sa.Column("submitted_eye", sa.String(8), nullable=False),
            sa.Column("detected_eye", sa.String(16), nullable=True),
            sa.Column("laterality_mismatch", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("similarity_score", sa.Float(), nullable=True),
            sa.Column("upload_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("quality_state", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("raw_output_json", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["run_id"], ["encounter_ai_inference_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["encounter_set_image_id"], ["encounter_set_images.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("run_id", "encounter_set_image_id", name="uq_encounter_ai_image_result"),
            sa.CheckConstraint("submitted_eye IN ('left','right')", name="ck_encounter_ai_image_submitted_eye"),
            sa.CheckConstraint("quality_state IN ('pending','gradable','ungradable','error')", name="ck_encounter_ai_image_quality_state"),
        )
        op.create_index("ix_encounter_ai_image_results_run_id", "encounter_ai_image_results", ["run_id"])
        op.create_index("ix_encounter_ai_image_results_encounter_set_image_id", "encounter_ai_image_results", ["encounter_set_image_id"])

    if "encounter_ai_target_results" not in _tables(conn):
        op.create_table(
            "encounter_ai_target_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("image_result_id", sa.Integer(), nullable=False),
            sa.Column("output_target_id", sa.Integer(), nullable=False),
            sa.Column("raw_label", sa.String(128), nullable=True),
            sa.Column("raw_score", sa.Float(), nullable=True),
            sa.Column("mapped_grade", sa.String(128), nullable=False),
            sa.Column("derivation_reason", sa.String(64), nullable=False),
            sa.Column("grade_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["image_result_id"], ["encounter_ai_image_results.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["output_target_id"], ["encounter_ai_output_targets.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("image_result_id", "output_target_id", name="uq_encounter_ai_target_result"),
            sa.CheckConstraint(
                "derivation_reason IN ('provider','similarity_threshold','provider_error')",
                name="ck_encounter_ai_target_derivation",
            ),
        )
        op.create_index("ix_encounter_ai_target_results_image_result_id", "encounter_ai_target_results", ["image_result_id"])
        op.create_index("ix_encounter_ai_target_results_output_target_id", "encounter_ai_target_results", ["output_target_id"])
        op.create_index("ix_encounter_ai_target_results_grade_id", "encounter_ai_target_results", ["grade_id"])

    conn.execute(text("""
        INSERT INTO ai_models (name, version, description, created_at)
        VALUES ('madhunetra_17aug2026', '17aug2026', 'MadhuNetrAI combined encounter-scoped DR and DME screening', now())
        ON CONFLICT (name, version) DO NOTHING
    """))
    conn.execute(text("""
        INSERT INTO ai_model_integrations
            (ai_model_id, provider, is_enabled, client_id, bearer_token, environment, config_json, created_at, updated_at)
        SELECT id, 'wai_dr_dme', false, 'vision-centre', '', 'staging',
               CAST(:config AS jsonb),
               now(), now()
        FROM ai_models WHERE name = 'madhunetra_17aug2026' AND version = '17aug2026'
        ON CONFLICT (provider) DO NOTHING
    """), {"config": json.dumps({
        "similarity_ungradable_threshold": 80,
        "maximum_images_per_eye": 10,
        "upload_retry_delays_seconds": [3, 5],
        "submit_timeout_seconds": 180,
        "mapping_version": "17aug2026",
        "normalization_version": "v1",
    })})
    conn.execute(text("""
        INSERT INTO ai_model_diseases (ai_model_id, disease_id, active, created_at)
        SELECT m.id, d.id, true, now()
        FROM ai_models m CROSS JOIN diseases d
        WHERE m.name = 'madhunetra_17aug2026' AND m.version = '17aug2026'
          AND lower(d.name) IN ('dr', 'diabetic retinopathy', 'dme')
        ON CONFLICT (ai_model_id, disease_id) DO UPDATE SET active = true
    """))
    conn.execute(text("""
        INSERT INTO encounter_ai_output_targets (ai_model_id, target_key, disease_id, label_mapping_json, active, created_at, updated_at)
        SELECT m.id, 'dr', d.id,
               CAST(:mapping AS jsonb),
               true, now(), now()
        FROM ai_models m JOIN diseases d ON lower(d.name) IN ('dr', 'diabetic retinopathy')
        WHERE m.name = 'madhunetra_17aug2026' AND m.version = '17aug2026'
        ORDER BY CASE WHEN lower(d.name) = 'dr' THEN 0 ELSE 1 END LIMIT 1
        ON CONFLICT (ai_model_id, target_key) DO NOTHING
    """), {"mapping": json.dumps({
        "No DR": "No DR",
        "Mild NPDR": "Mild DR",
        "Moderate NPDR": "Moderate NPDR",
        "Severe NPDR": "Severe NPDR",
        "PDR": "PDR",
    })})
    conn.execute(text("""
        INSERT INTO encounter_ai_output_targets (ai_model_id, target_key, disease_id, label_mapping_json, active, created_at, updated_at)
        SELECT m.id, 'dme', d.id,
               CAST(:mapping AS jsonb),
               true, now(), now()
        FROM ai_models m JOIN diseases d ON lower(d.name) = 'dme'
        WHERE m.name = 'madhunetra_17aug2026' AND m.version = '17aug2026'
        LIMIT 1
        ON CONFLICT (ai_model_id, target_key) DO NOTHING
    """), {"mapping": json.dumps({
        "No DME": "M0 No DME",
        "DME": "M1 Referable Diabetic Maculopathy",
    })})


def downgrade() -> None:
    conn = op.get_bind()
    for table in (
        "encounter_ai_target_results",
        "encounter_ai_image_results",
        "encounter_ai_inference_runs",
        "encounter_ai_output_targets",
        "project_encounter_ai_workflows",
    ):
        if table in _tables(conn):
            op.drop_table(table)
    conn.execute(text("""
        DELETE FROM ai_model_diseases
        WHERE ai_model_id IN (SELECT id FROM ai_models WHERE name='madhunetra_17aug2026' AND version='17aug2026');
        DELETE FROM ai_model_integrations WHERE provider='wai_dr_dme';
        DELETE FROM ai_models WHERE name='madhunetra_17aug2026' AND version='17aug2026';
    """))
    op.execute("ALTER TABLE ai_model_integrations DROP CONSTRAINT IF EXISTS ck_ai_model_integration_provider_valid")
    op.create_check_constraint(
        "ck_ai_model_integration_provider_valid", "ai_model_integrations", "provider IN ('wadhwani_glaucoma')"
    )
    for column in ("config_json", "access_token_encrypted", "environment", "api_base_url"):
        if column in _columns(conn, "ai_model_integrations"):
            op.drop_column("ai_model_integrations", column)
