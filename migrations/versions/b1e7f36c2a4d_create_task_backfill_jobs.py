"""create task backfill jobs table

Revision ID: b1e7f36c2a4d
Revises: e6f3a2c1d9ab
Create Date: 2026-01-23
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b1e7f36c2a4d"
down_revision = "e6f3a2c1d9ab"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'task_backfill_jobs') THEN
                CREATE TABLE task_backfill_jobs (
                    id SERIAL PRIMARY KEY,
                    status VARCHAR(32) NOT NULL DEFAULT 'queued',
                    requested_limit INTEGER,
                    created_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    total_candidates INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    started_at TIMESTAMPTZ,
                    finished_at TIMESTAMPTZ,
                    created_by_id INTEGER REFERENCES users(id),
                    created_by_username VARCHAR(150),
                    hospital_id INTEGER REFERENCES hospitals(id),
                    allowed_lab_unit_ids TEXT
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_task_backfill_job_status'
            ) THEN
                ALTER TABLE task_backfill_jobs
                ADD CONSTRAINT ck_task_backfill_job_status
                CHECK (status IN ('queued','running','completed','failed'));
            END IF;
        END $$;
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_backfill_jobs_status ON task_backfill_jobs (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_backfill_jobs_created_at ON task_backfill_jobs (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_backfill_jobs_hospital_id ON task_backfill_jobs (hospital_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_task_backfill_jobs_created_by_id ON task_backfill_jobs (created_by_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS task_backfill_jobs CASCADE")
