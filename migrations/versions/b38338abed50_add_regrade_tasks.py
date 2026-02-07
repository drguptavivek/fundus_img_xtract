"""add regrade tasks

Revision ID: b38338abed50
Revises: 086d81edd08f
Create Date: 2026-02-07 12:57:34.959264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b38338abed50'
down_revision: Union[str, Sequence[str], None] = '086d81edd08f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'regrade_tasks') THEN
                CREATE TABLE regrade_tasks (
                    id SERIAL PRIMARY KEY,
                    uuid VARCHAR(36) NOT NULL,
                    source_task_id INTEGER NOT NULL REFERENCES grading_tasks(id) ON DELETE CASCADE,
                    disease_id INTEGER NOT NULL REFERENCES diseases(id),
                    lab_unit_id INTEGER NOT NULL REFERENCES lab_units(id),
                    assigned_to_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    status VARCHAR(24) NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
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
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_regrade_task_status_valid'
            ) THEN
                ALTER TABLE regrade_tasks
                ADD CONSTRAINT ck_regrade_task_status_valid
                CHECK (status IN ('regrade_pending','regrade_done'));
            END IF;
        END $$;
        """
    )

    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_regrade_tasks_uuid ON regrade_tasks (uuid);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regrade_tasks_source_task_id ON regrade_tasks (source_task_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regrade_tasks_disease_id ON regrade_tasks (disease_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regrade_tasks_lab_unit_id ON regrade_tasks (lab_unit_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regrade_tasks_assigned_to_user_id ON regrade_tasks (assigned_to_user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regrade_tasks_created_by_user_id ON regrade_tasks (created_by_user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regrade_tasks_status ON regrade_tasks (status);")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_regrade_tasks_pending_source
        ON regrade_tasks (source_task_id)
        WHERE status = 'regrade_pending';
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_grade_role_slot_valid'
            ) THEN
                ALTER TABLE grades DROP CONSTRAINT ck_grade_role_slot_valid;
            END IF;
            ALTER TABLE grades
            ADD CONSTRAINT ck_grade_role_slot_valid
            CHECK (role_slot IN ('resident','resident2','arbitrator','ai','review','regrade_adjudicator'));
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_consensus_method_valid'
            ) THEN
                ALTER TABLE consensus DROP CONSTRAINT ck_consensus_method_valid;
            END IF;
            ALTER TABLE consensus
            ADD CONSTRAINT ck_consensus_method_valid
            CHECK (method IN ('match','adjudication','task_review','regrade'));
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE consensus DROP CONSTRAINT IF EXISTS ck_consensus_method_valid;")
    op.execute(
        """
        ALTER TABLE consensus
        ADD CONSTRAINT ck_consensus_method_valid
        CHECK (method IN ('match','adjudication','task_review'));
        """
    )
    op.execute("ALTER TABLE grades DROP CONSTRAINT IF EXISTS ck_grade_role_slot_valid;")
    op.execute(
        """
        ALTER TABLE grades
        ADD CONSTRAINT ck_grade_role_slot_valid
        CHECK (role_slot IN ('resident','resident2','arbitrator','ai','review'));
        """
    )

    op.execute("DROP INDEX IF EXISTS ux_regrade_tasks_pending_source;")
    op.execute("DROP INDEX IF EXISTS ix_regrade_tasks_status;")
    op.execute("DROP INDEX IF EXISTS ix_regrade_tasks_created_by_user_id;")
    op.execute("DROP INDEX IF EXISTS ix_regrade_tasks_assigned_to_user_id;")
    op.execute("DROP INDEX IF EXISTS ix_regrade_tasks_lab_unit_id;")
    op.execute("DROP INDEX IF EXISTS ix_regrade_tasks_disease_id;")
    op.execute("DROP INDEX IF EXISTS ix_regrade_tasks_source_task_id;")
    op.execute("DROP INDEX IF EXISTS ix_regrade_tasks_uuid;")
    op.execute("DROP TABLE IF EXISTS regrade_tasks;")
