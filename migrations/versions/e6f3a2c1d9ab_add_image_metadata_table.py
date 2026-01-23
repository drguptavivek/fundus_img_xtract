"""add image metadata table

Revision ID: e6f3a2c1d9ab
Revises: ('45cf0f839a1c', '79cc3b6a36ee', 'd7e3fb45da1d')
Create Date: 2026-01-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f3a2c1d9ab"
down_revision: Union[str, Sequence[str], None] = (
    "45cf0f839a1c",
    "79cc3b6a36ee",
    "d7e3fb45da1d",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'image_metadata') THEN
                CREATE TABLE image_metadata (
                    id SERIAL PRIMARY KEY,
                    image_uuid VARCHAR(36) NOT NULL,
                    image_variant VARCHAR(8) NOT NULL,
                    encounter_file_id INTEGER REFERENCES encounter_files(id) ON DELETE CASCADE,
                    direct_image_upload_id INTEGER REFERENCES direct_image_uploads(id) ON DELETE CASCADE,
                    width INTEGER,
                    height INTEGER,
                    format VARCHAR(16),
                    mode VARCHAR(16),
                    bit_depth INTEGER,
                    is_grayscale BOOLEAN,
                    has_alpha BOOLEAN,
                    file_size_bytes INTEGER,
                    dpi_x FLOAT,
                    dpi_y FLOAT,
                    avg_luminance FLOAT,
                    max_luminance FLOAT,
                    luminance_std FLOAT,
                    mean_r FLOAT,
                    mean_g FLOAT,
                    mean_b FLOAT,
                    median_r FLOAT,
                    median_g FLOAT,
                    median_b FLOAT,
                    histogram_json TEXT,
                    exif_json TEXT,
                    iptc_json TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CONSTRAINT uq_image_metadata_uuid_variant UNIQUE (image_uuid, image_variant),
                    CONSTRAINT ck_image_metadata_variant CHECK (image_variant IN ('orig','edited'))
                );
            END IF;
        END $$;
        """
    )

    conn = op.get_bind()
    if not op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_image_uuid"):
        op.create_index("ix_image_metadata_image_uuid", "image_metadata", ["image_uuid"], unique=False)
    if not op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_image_variant"):
        op.create_index("ix_image_metadata_image_variant", "image_metadata", ["image_variant"], unique=False)
    if not op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_encounter_file_id"):
        op.create_index("ix_image_metadata_encounter_file_id", "image_metadata", ["encounter_file_id"], unique=False)
    if not op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_direct_image_upload_id"):
        op.create_index("ix_image_metadata_direct_image_upload_id", "image_metadata", ["direct_image_upload_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    if op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_direct_image_upload_id"):
        op.drop_index("ix_image_metadata_direct_image_upload_id", table_name="image_metadata")
    if op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_encounter_file_id"):
        op.drop_index("ix_image_metadata_encounter_file_id", table_name="image_metadata")
    if op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_image_variant"):
        op.drop_index("ix_image_metadata_image_variant", table_name="image_metadata")
    if op.get_context().dialect.has_index(conn, "image_metadata", "ix_image_metadata_image_uuid"):
        op.drop_index("ix_image_metadata_image_uuid", table_name="image_metadata")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'image_metadata') THEN
                DROP TABLE image_metadata;
            END IF;
        END $$;
        """
    )
