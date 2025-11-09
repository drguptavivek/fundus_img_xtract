"""create_materialized_view_refresh_tracking

Revision ID: b3ab758d04e3
Revises: c99df7413504
Create Date: 2025-11-10 01:21:58.974560

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3ab758d04e3'
down_revision: Union[str, Sequence[str], None] = 'c99df7413504'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create table to track materialized view refresh timestamps
    op.execute("""
        CREATE TABLE materialized_view_refresh_log (
            id SERIAL PRIMARY KEY,
            materialized_view_name VARCHAR(255) NOT NULL DEFAULT 'mvw_grading_data_all',
            refresh_type VARCHAR(50) NOT NULL, -- 'scheduled', 'manual', 'startup'
            refresh_started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            refresh_completed_at TIMESTAMP WITH TIME ZONE,
            refresh_duration_seconds FLOAT,
            success BOOLEAN NOT NULL DEFAULT FALSE,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Create index for efficient querying
        CREATE INDEX idx_mv_refresh_log_view_name ON materialized_view_refresh_log(materialized_view_name);
        CREATE INDEX idx_mv_refresh_log_completed_at ON materialized_view_refresh_log(refresh_completed_at);
        CREATE INDEX idx_mv_refresh_log_success ON materialized_view_refresh_log(success);

        -- Create trigger to update updated_at column
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language plpgsql;

        CREATE TRIGGER update_materialized_view_refresh_log_updated_at
            BEFORE UPDATE ON materialized_view_refresh_log
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)

def downgrade() -> None:
    """Downgrade schema."""
    # Drop the trigger first
    op.execute("DROP TRIGGER IF EXISTS update_materialized_view_refresh_log_updated_at ON materialized_view_refresh_log;")

    # Drop the function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_mv_refresh_log_success;")
    op.execute("DROP INDEX IF EXISTS idx_mv_refresh_log_completed_at;")
    op.execute("DROP INDEX IF EXISTS idx_mv_refresh_log_view_name;")

    # Drop the table
    op.execute("DROP TABLE IF EXISTS materialized_view_refresh_log;")
