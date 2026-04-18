"""add ai model integrations and inference runs

Revision ID: a4c1d9e7b2f3
Revises: 7c1e9bd12f44
Create Date: 2026-02-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a4c1d9e7b2f3"
down_revision: Union[str, Sequence[str], None] = "7c1e9bd12f44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_model_integrations') THEN
                CREATE TABLE ai_model_integrations (
                    id SERIAL PRIMARY KEY,
                    ai_model_id INTEGER NOT NULL UNIQUE REFERENCES ai_models(id) ON DELETE CASCADE,
                    provider VARCHAR(64) NOT NULL,
                    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    client_id VARCHAR(255) NOT NULL,
                    bearer_token TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_ai_model_integrations_provider UNIQUE (provider),
                    CONSTRAINT ck_ai_model_integration_provider_valid CHECK (provider IN ('wadhwani_glaucoma'))
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_inference_runs') THEN
                CREATE TABLE ai_inference_runs (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES grading_tasks(id) ON DELETE CASCADE,
                    ai_model_id INTEGER NOT NULL REFERENCES ai_models(id) ON DELETE CASCADE,
                    integration_id INTEGER REFERENCES ai_model_integrations(id) ON DELETE SET NULL,
                    requested_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    source VARCHAR(32) NOT NULL DEFAULT 'internal',
                    status VARCHAR(32) NOT NULL DEFAULT 'queued',
                    external_request_id VARCHAR(128),
                    prediction_id VARCHAR(128),
                    remote_filename VARCHAR(255),
                    remote_content_type VARCHAR(128),
                    http_status INTEGER,
                    request_manifest_json JSONB,
                    initialize_response_json JSONB,
                    execute_response_json JSONB,
                    error_code VARCHAR(128),
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP WITH TIME ZONE,
                    finished_at TIMESTAMP WITH TIME ZONE,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT ck_ai_inference_run_source_valid CHECK (source IN ('internal','mobile','backfill')),
                    CONSTRAINT ck_ai_inference_run_status_valid CHECK (status IN ('queued','running','success','failed'))
                );
            END IF;
        END $$;
        """
    )

    conn = op.get_bind()
    if not op.get_context().dialect.has_index(conn, "ai_model_integrations", "ix_ai_model_integrations_ai_model_id"):
        op.create_index("ix_ai_model_integrations_ai_model_id", "ai_model_integrations", ["ai_model_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_model_integrations", "ix_ai_model_integrations_provider"):
        op.create_index("ix_ai_model_integrations_provider", "ai_model_integrations", ["provider"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_model_integrations", "ix_ai_model_integrations_is_enabled"):
        op.create_index("ix_ai_model_integrations_is_enabled", "ai_model_integrations", ["is_enabled"], unique=False)

    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_task_id"):
        op.create_index("ix_ai_inference_runs_task_id", "ai_inference_runs", ["task_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_ai_model_id"):
        op.create_index("ix_ai_inference_runs_ai_model_id", "ai_inference_runs", ["ai_model_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_integration_id"):
        op.create_index("ix_ai_inference_runs_integration_id", "ai_inference_runs", ["integration_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_requested_by_user_id"):
        op.create_index("ix_ai_inference_runs_requested_by_user_id", "ai_inference_runs", ["requested_by_user_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_source"):
        op.create_index("ix_ai_inference_runs_source", "ai_inference_runs", ["source"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_status"):
        op.create_index("ix_ai_inference_runs_status", "ai_inference_runs", ["status"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_external_request_id"):
        op.create_index("ix_ai_inference_runs_external_request_id", "ai_inference_runs", ["external_request_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_prediction_id"):
        op.create_index("ix_ai_inference_runs_prediction_id", "ai_inference_runs", ["prediction_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_task_model_created"):
        op.create_index(
            "ix_ai_inference_runs_task_model_created",
            "ai_inference_runs",
            ["task_id", "ai_model_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()

    if op.get_context().dialect.has_index(conn, "ai_inference_runs", "ix_ai_inference_runs_task_model_created"):
        op.drop_index("ix_ai_inference_runs_task_model_created", table_name="ai_inference_runs")
    for index_name in (
        "ix_ai_inference_runs_prediction_id",
        "ix_ai_inference_runs_external_request_id",
        "ix_ai_inference_runs_status",
        "ix_ai_inference_runs_source",
        "ix_ai_inference_runs_requested_by_user_id",
        "ix_ai_inference_runs_integration_id",
        "ix_ai_inference_runs_ai_model_id",
        "ix_ai_inference_runs_task_id",
    ):
        if op.get_context().dialect.has_index(conn, "ai_inference_runs", index_name):
            op.drop_index(index_name, table_name="ai_inference_runs")

    for index_name in (
        "ix_ai_model_integrations_is_enabled",
        "ix_ai_model_integrations_provider",
        "ix_ai_model_integrations_ai_model_id",
    ):
        if op.get_context().dialect.has_index(conn, "ai_model_integrations", index_name):
            op.drop_index(index_name, table_name="ai_model_integrations")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_inference_runs') THEN
                DROP TABLE ai_inference_runs;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_model_integrations') THEN
                DROP TABLE ai_model_integrations;
            END IF;
        END $$;
        """
    )
