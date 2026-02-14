"""expand_viewer_contrast_range

Revision ID: 216d32163cf6
Revises: 3c4f2a9b7e21
Create Date: 2026-02-14 03:50:25.030340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '216d32163cf6'
down_revision: Union[str, Sequence[str], None] = '3c4f2a9b7e21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_loupe_size'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_loupe_size;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_loupe_size
                CHECK (loupe_size >= 50 AND loupe_size <= 1000);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_loupe_zoom'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_loupe_zoom;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_loupe_zoom
                CHECK (loupe_zoom >= 0.5 AND loupe_zoom <= 8.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_zoom'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_zoom;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_zoom
                CHECK (zoom >= 10 AND zoom <= 800);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_pan_x'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_pan_x;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_pan_x
                CHECK (pan_x >= -1200 AND pan_x <= 1200);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_pan_y'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_pan_y;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_pan_y
                CHECK (pan_y >= -1200 AND pan_y <= 1200);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_brightness'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_brightness;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_brightness
                CHECK (brightness >= 0 AND brightness <= 10.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_contrast'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_contrast;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_contrast
                CHECK (contrast >= 0 AND contrast <= 10.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_filter'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_filter;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_filter
                CHECK (filter IN ('none','redfree','greenboost','bluemono','gray','contrast','enhance','greenchannel','blueonly','redgreenfree','greenfree'));
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_loupe_size'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_loupe_size;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_loupe_size
                CHECK (loupe_size >= 50 AND loupe_size <= 1000);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_loupe_zoom'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_loupe_zoom;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_loupe_zoom
                CHECK (loupe_zoom >= 0.5 AND loupe_zoom <= 8.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_zoom'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_zoom;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_zoom
                CHECK (zoom >= 10 AND zoom <= 800);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_pan_x'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_pan_x;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_pan_x
                CHECK (pan_x >= -1200 AND pan_x <= 1200);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_pan_y'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_pan_y;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_pan_y
                CHECK (pan_y >= -1200 AND pan_y <= 1200);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_brightness'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_brightness;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_brightness
                CHECK (brightness >= 0 AND brightness <= 10.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_contrast'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_contrast;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_contrast
                CHECK (contrast >= 0 AND contrast <= 10.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_filter'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_filter;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_filter
                CHECK (filter IN ('none','redfree','greenboost','bluemono','gray','contrast','enhance','greenchannel','blueonly','redgreenfree','greenfree'));
        END $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_loupe_size'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_loupe_size;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_loupe_size
                CHECK (loupe_size >= 100 AND loupe_size <= 500);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_loupe_zoom'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_loupe_zoom;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_loupe_zoom
                CHECK (loupe_zoom >= 1.0 AND loupe_zoom <= 4.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_zoom'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_zoom;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_zoom
                CHECK (zoom >= 40 AND zoom <= 500);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_pan_x'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_pan_x;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_pan_x
                CHECK (pan_x >= -600 AND pan_x <= 600);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_pan_y'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_pan_y;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_pan_y
                CHECK (pan_y >= -600 AND pan_y <= 600);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_brightness'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_brightness;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_brightness
                CHECK (brightness >= 0.5 AND brightness <= 5.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_contrast'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_contrast;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_contrast
                CHECK (contrast >= 0.5 AND contrast <= 1.5);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_settings_filter'
            ) THEN
                ALTER TABLE viewer_settings DROP CONSTRAINT ck_viewer_settings_filter;
            END IF;
            ALTER TABLE viewer_settings
                ADD CONSTRAINT ck_viewer_settings_filter
                CHECK (filter IN ('none','redfree','greenboost','bluemono','gray','contrast'));
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_loupe_size'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_loupe_size;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_loupe_size
                CHECK (loupe_size >= 100 AND loupe_size <= 500);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_loupe_zoom'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_loupe_zoom;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_loupe_zoom
                CHECK (loupe_zoom >= 1.0 AND loupe_zoom <= 4.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_zoom'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_zoom;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_zoom
                CHECK (zoom >= 40 AND zoom <= 500);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_pan_x'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_pan_x;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_pan_x
                CHECK (pan_x >= -600 AND pan_x <= 600);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_pan_y'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_pan_y;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_pan_y
                CHECK (pan_y >= -600 AND pan_y <= 600);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_brightness'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_brightness;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_brightness
                CHECK (brightness >= 0.5 AND brightness <= 5.0);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_contrast'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_contrast;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_contrast
                CHECK (contrast >= 0.5 AND contrast <= 1.5);

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_viewer_presets_filter'
            ) THEN
                ALTER TABLE viewer_presets DROP CONSTRAINT ck_viewer_presets_filter;
            END IF;
            ALTER TABLE viewer_presets
                ADD CONSTRAINT ck_viewer_presets_filter
                CHECK (filter IN ('none','redfree','greenboost','bluemono','gray','contrast'));
        END $$;
        """
    )
