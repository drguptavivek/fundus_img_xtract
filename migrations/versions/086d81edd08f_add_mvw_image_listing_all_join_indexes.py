"""add mvw_image_listing_all join indexes

Revision ID: 086d81edd08f
Revises: 2a251986df60
Create Date: 2026-02-07 10:33:03.844895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '086d81edd08f'
down_revision: Union[str, Sequence[str], None] = '2a251986df60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'mvw_image_listing_all') THEN
                CREATE INDEX IF NOT EXISTS idx_image_listing_direct_upload_id
                    ON mvw_image_listing_all(direct_image_upload_id);
                CREATE INDEX IF NOT EXISTS idx_image_listing_encounter_file_id
                    ON mvw_image_listing_all(encounter_file_id);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'mvw_image_listing_all') THEN
                DROP INDEX IF EXISTS idx_image_listing_direct_upload_id;
                DROP INDEX IF EXISTS idx_image_listing_encounter_file_id;
            END IF;
        END $$;
        """
    )
