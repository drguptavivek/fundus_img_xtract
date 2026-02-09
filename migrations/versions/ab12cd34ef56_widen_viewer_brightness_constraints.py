"""Widen viewer brightness constraints.

Revision ID: ab12cd34ef56
Revises: 9a3b1d2c4e5f
Create Date: 2026-02-09 10:51:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "9a3b1d2c4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_viewer_settings_brightness'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_brightness;
            END IF;

            ALTER TABLE viewer_settings
            ADD CONSTRAINT ck_viewer_settings_brightness
            CHECK (brightness >= 0.5 AND brightness <= 5.0);

            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_viewer_presets_brightness'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_brightness;
            END IF;

            ALTER TABLE viewer_presets
            ADD CONSTRAINT ck_viewer_presets_brightness
            CHECK (brightness >= 0.5 AND brightness <= 5.0);
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_viewer_settings_brightness'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_brightness;
            END IF;

            ALTER TABLE viewer_settings
            ADD CONSTRAINT ck_viewer_settings_brightness
            CHECK (brightness >= 0.5 AND brightness <= 1.5);

            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_viewer_presets_brightness'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_brightness;
            END IF;

            ALTER TABLE viewer_presets
            ADD CONSTRAINT ck_viewer_presets_brightness
            CHECK (brightness >= 0.5 AND brightness <= 1.5);
        END $$;
        """
    )
