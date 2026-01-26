"""Remove path_prefix from s3_configs (global prefix enforced).

Revision ID: f0c1d2e3a4b5
Revises: e1561a8ecbe7
Create Date: 2026-01-26
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f0c1d2e3a4b5"
down_revision = "e1561a8ecbe7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 's3_configs'
                  AND column_name = 'path_prefix'
            ) THEN
                ALTER TABLE s3_configs DROP COLUMN path_prefix;
            END IF;
        END $$;
        """
    )


def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 's3_configs'
                  AND column_name = 'path_prefix'
            ) THEN
                ALTER TABLE s3_configs ADD COLUMN path_prefix VARCHAR(200);
            END IF;
        END $$;
        """
    )
