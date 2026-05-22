"""deactivate duplicate eye metadata field

Revision ID: f5a4b3c2d1e0
Revises: e4f3a2b1c0d9
Create Date: 2026-05-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "f5a4b3c2d1e0"
down_revision: Union[str, Sequence[str], None] = "e4f3a2b1c0d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "upload_metadata_field_definitions"
ENCOUNTER_SET_TYPES_TABLE = "encounter_set_types"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE_NAME not in inspector.get_table_names():
        return

    eye_is_used = False
    if ENCOUNTER_SET_TYPES_TABLE in inspector.get_table_names():
        eye_is_used = bool(
            bind.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM encounter_set_types
                    WHERE metadata_schema_json::jsonb @> '{"fields":[{"key":"eye"}]}'::jsonb
                    LIMIT 1
                    """
                )
            ).scalar()
        )

    if not eye_is_used:
        bind.execute(
            sa.text(
                """
                UPDATE upload_metadata_field_definitions
                SET active = false
                WHERE key = 'eye'
                  AND scope = 'image'
                  AND active IS true
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE_NAME not in inspector.get_table_names():
        return
    bind.execute(
        sa.text(
            """
            UPDATE upload_metadata_field_definitions
            SET active = true
            WHERE key = 'eye'
              AND scope = 'image'
            """
        )
    )
