"""add pii detection jobs

Revision ID: 7b3c2f9d4e1a
Revises: 3598c141c1a7
Create Date: 2026-01-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7b3c2f9d4e1a"
down_revision: Union[str, Sequence[str], None] = "3598c141c1a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pii_detection_jobs') THEN
                CREATE TABLE pii_detection_jobs (
                    id SERIAL PRIMARY KEY,
                    image_uuid VARCHAR(36) NOT NULL,
                    image_variant VARCHAR(16) NOT NULL,
                    image_path TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'queued',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    source VARCHAR(16) NOT NULL DEFAULT 'auto',
                    error_message TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP WITH TIME ZONE,
                    finished_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT ck_pii_detection_job_status CHECK (status IN ('queued','running','completed','failed')),
                    CONSTRAINT ck_pii_detection_job_variant CHECK (image_variant IN ('orig','edited')),
                    CONSTRAINT ck_pii_detection_job_source CHECK (source IN ('auto','manual'))
                );
            END IF;
        END $$;
        """
    )

    conn = op.get_bind()
    if not op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_image_uuid"):
        op.create_index("ix_pii_detection_jobs_image_uuid", "pii_detection_jobs", ["image_uuid"], unique=False)
    if not op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_image_variant"):
        op.create_index("ix_pii_detection_jobs_image_variant", "pii_detection_jobs", ["image_variant"], unique=False)
    if not op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_status"):
        op.create_index("ix_pii_detection_jobs_status", "pii_detection_jobs", ["status"], unique=False)
    if not op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_status_created"):
        op.create_index("ix_pii_detection_jobs_status_created", "pii_detection_jobs", ["status", "created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    if op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_status_created"):
        op.drop_index("ix_pii_detection_jobs_status_created", table_name="pii_detection_jobs")
    if op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_status"):
        op.drop_index("ix_pii_detection_jobs_status", table_name="pii_detection_jobs")
    if op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_image_variant"):
        op.drop_index("ix_pii_detection_jobs_image_variant", table_name="pii_detection_jobs")
    if op.get_context().dialect.has_index(conn, "pii_detection_jobs", "ix_pii_detection_jobs_image_uuid"):
        op.drop_index("ix_pii_detection_jobs_image_uuid", table_name="pii_detection_jobs")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pii_detection_jobs') THEN
                DROP TABLE pii_detection_jobs;
            END IF;
        END $$;
        """
    )
