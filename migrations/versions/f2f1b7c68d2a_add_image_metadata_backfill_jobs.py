"""add image metadata backfill jobs

Revision ID: f2f1b7c68d2a
Revises: e6f3a2c1d9ab
Create Date: 2026-01-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2f1b7c68d2a"
down_revision: Union[str, Sequence[str], None] = "e6f3a2c1d9ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'image_metadata_backfill_jobs') THEN
                CREATE TABLE image_metadata_backfill_jobs (
                    id SERIAL PRIMARY KEY,
                    status VARCHAR(32) NOT NULL DEFAULT 'queued',
                    requested_limit INTEGER,
                    metadata_created_count INTEGER NOT NULL DEFAULT 0,
                    pii_created_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    total_candidates INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP WITH TIME ZONE,
                    finished_at TIMESTAMP WITH TIME ZONE,
                    created_by_id INTEGER REFERENCES users(id),
                    created_by_username VARCHAR(150),
                    hospital_id INTEGER REFERENCES hospitals(id),
                    allowed_lab_unit_ids TEXT,
                    CONSTRAINT ck_image_metadata_backfill_job_status CHECK (status IN ('queued','running','completed','failed'))
                );
            END IF;
        END $$;
        """
    )

    conn = op.get_bind()
    if not op.get_context().dialect.has_index(conn, "image_metadata_backfill_jobs", "ix_image_metadata_backfill_jobs_status"):
        op.create_index(
            "ix_image_metadata_backfill_jobs_status",
            "image_metadata_backfill_jobs",
            ["status"],
            unique=False,
        )
    if not op.get_context().dialect.has_index(conn, "image_metadata_backfill_jobs", "ix_image_metadata_backfill_jobs_hospital_created"):
        op.create_index(
            "ix_image_metadata_backfill_jobs_hospital_created",
            "image_metadata_backfill_jobs",
            ["hospital_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    if op.get_context().dialect.has_index(conn, "image_metadata_backfill_jobs", "ix_image_metadata_backfill_jobs_hospital_created"):
        op.drop_index("ix_image_metadata_backfill_jobs_hospital_created", table_name="image_metadata_backfill_jobs")
    if op.get_context().dialect.has_index(conn, "image_metadata_backfill_jobs", "ix_image_metadata_backfill_jobs_status"):
        op.drop_index("ix_image_metadata_backfill_jobs_status", table_name="image_metadata_backfill_jobs")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'image_metadata_backfill_jobs') THEN
                DROP TABLE image_metadata_backfill_jobs;
            END IF;
        END $$;
        """
    )
