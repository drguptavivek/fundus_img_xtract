"""add_multi_tenant_s3_support

Revision ID: 4b7b1e398a79
Revises: 8d0f6a3c2b11
Create Date: 2026-01-25 06:04:36.868799

Multi-tenant S3-compatible storage with BYOK (Bring Your Own Key):
- Hospital-scoped S3 configs (one active config per hospital)
- Provider support: R2, Hetzner, AWS S3, Google Cloud Storage, Azure Blob, MinIO, Other
- PyNaCl encrypted credentials with hospital-derived keys
- HMAC URL signing pepper for hospital isolation
- Auto-rotation support with timezone-aware scheduling
- Binary fallback policy: never (fail hard) or always (allow local)

IDEMPOTENT: Safe to run multiple times.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '4b7b1e398a79'
down_revision: Union[str, Sequence[str], None] = '8d0f6a3c2b11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add multi-tenant S3 storage support.

    IDEMPOTENT: Checks for existence before creating tables/columns.
    """
    conn = op.get_bind()

    # ========================================================================
    # 1. Create s3_configs table
    # ========================================================================
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 's3_configs') THEN
                CREATE TABLE s3_configs (
                    id SERIAL PRIMARY KEY,
                    hospital_id INTEGER NOT NULL REFERENCES hospitals(id) ON DELETE RESTRICT,
                    provider VARCHAR(20) NOT NULL DEFAULT 'other',
                    name VARCHAR(100) NOT NULL,
                    bucket_name VARCHAR(255) NOT NULL,
                    region VARCHAR(50) NOT NULL,
                    endpoint_url VARCHAR(500),
                    path_prefix VARCHAR(200),
                    access_key_encrypted TEXT NOT NULL,
                    secret_key_encrypted TEXT NOT NULL,
                    url_signing_pepper TEXT NOT NULL,
                    url_signing_pepper_previous TEXT,
                    pepper_rotated_at TIMESTAMP WITH TIME ZONE,
                    auto_rotate_pepper BOOLEAN NOT NULL DEFAULT FALSE,
                    rotation_time TIME,
                    rotation_timezone VARCHAR(64),
                    rotation_last_run TIMESTAMP WITH TIME ZONE,
                    fallback_policy VARCHAR(10) NOT NULL DEFAULT 'never',
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    created_by_id INTEGER NOT NULL REFERENCES users(id),

                    CONSTRAINT uq_s3_config_hospital_name UNIQUE (hospital_id, name),
                    CONSTRAINT ck_s3_config_not_active_and_archived
                        CHECK (NOT (is_active = TRUE AND is_archived = TRUE)),
                    CONSTRAINT ck_s3_config_fallback_policy
                        CHECK (fallback_policy IN ('never', 'always')),
                    CONSTRAINT ck_s3_config_provider
                        CHECK (provider IN ('r2', 'hetzner', 'aws', 'gcp', 'azure', 'minio', 'other'))
                );

                -- Indexes
                CREATE INDEX ix_s3_configs_hospital_id ON s3_configs(hospital_id);
                CREATE INDEX ix_s3_configs_is_active ON s3_configs(is_active) WHERE is_active = TRUE;
                CREATE INDEX ix_s3_configs_is_archived ON s3_configs(is_archived);

                -- Partial index for active configs per hospital (only one active per hospital)
                CREATE UNIQUE INDEX ix_s3_config_active_per_hospital
                    ON s3_configs(hospital_id)
                    WHERE is_active = TRUE;

                -- Composite index for active configs with hospital
                CREATE INDEX ix_s3_configs_active
                    ON s3_configs(hospital_id, is_active)
                    WHERE is_active = TRUE;

                -- Index for auto-rotation task
                CREATE INDEX ix_s3_configs_auto_rotate
                    ON s3_configs(auto_rotate_pepper, rotation_last_run)
                    WHERE auto_rotate_pepper = TRUE;
            END IF;
        END $$;
    """))

    # ========================================================================
    # 2. Add S3 columns to direct_image_uploads
    # ========================================================================
    conn.execute(text("""
        DO $$
        BEGIN
            -- s3_config_id
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'direct_image_uploads' AND column_name = 's3_config_id'
            ) THEN
                ALTER TABLE direct_image_uploads
                ADD COLUMN s3_config_id INTEGER REFERENCES s3_configs(id);

                CREATE INDEX ix_direct_image_uploads_s3_config_id
                    ON direct_image_uploads(s3_config_id);
            END IF;

            -- s3_object_key
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'direct_image_uploads' AND column_name = 's3_object_key'
            ) THEN
                ALTER TABLE direct_image_uploads
                ADD COLUMN s3_object_key VARCHAR(500);
            END IF;

            -- s3_object_key_edited
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'direct_image_uploads' AND column_name = 's3_object_key_edited'
            ) THEN
                ALTER TABLE direct_image_uploads
                ADD COLUMN s3_object_key_edited VARCHAR(500);
            END IF;

            -- s3_object_key_thumbnail
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'direct_image_uploads' AND column_name = 's3_object_key_thumbnail'
            ) THEN
                ALTER TABLE direct_image_uploads
                ADD COLUMN s3_object_key_thumbnail VARCHAR(500);
            END IF;

            -- s3_object_key_edited_thumbnail
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'direct_image_uploads' AND column_name = 's3_object_key_edited_thumbnail'
            ) THEN
                ALTER TABLE direct_image_uploads
                ADD COLUMN s3_object_key_edited_thumbnail VARCHAR(500);
            END IF;

            -- Composite indexes for S3 queries
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'direct_image_uploads' AND indexname = 'ix_diu_s3_config_uuid'
            ) THEN
                CREATE INDEX ix_diu_s3_config_uuid
                    ON direct_image_uploads(s3_config_id, uuid);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'direct_image_uploads' AND indexname = 'ix_diu_s3_config_created'
            ) THEN
                CREATE INDEX ix_diu_s3_config_created
                    ON direct_image_uploads(s3_config_id, created_at);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'direct_image_uploads' AND indexname = 'ix_diu_hospital_id'
            ) THEN
                CREATE INDEX ix_diu_hospital_id
                    ON direct_image_uploads(hospital_id);
            END IF;
        END $$;
    """))

    # ========================================================================
    # 3. Add S3 columns to encounter_files
    # ========================================================================
    conn.execute(text("""
        DO $$
        BEGIN
            -- hospital_id
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'encounter_files' AND column_name = 'hospital_id'
            ) THEN
                ALTER TABLE encounter_files
                ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id);

                CREATE INDEX ix_encounter_files_hospital_id
                    ON encounter_files(hospital_id);
            END IF;

            -- s3_config_id
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'encounter_files' AND column_name = 's3_config_id'
            ) THEN
                ALTER TABLE encounter_files
                ADD COLUMN s3_config_id INTEGER REFERENCES s3_configs(id);

                CREATE INDEX ix_encounter_files_s3_config_id
                    ON encounter_files(s3_config_id);
            END IF;

            -- s3_object_key
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'encounter_files' AND column_name = 's3_object_key'
            ) THEN
                ALTER TABLE encounter_files
                ADD COLUMN s3_object_key VARCHAR(500);
            END IF;

            -- s3_object_key_thumbnail
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'encounter_files' AND column_name = 's3_object_key_thumbnail'
            ) THEN
                ALTER TABLE encounter_files
                ADD COLUMN s3_object_key_thumbnail VARCHAR(500);
            END IF;

            -- Composite indexes for S3 queries
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'encounter_files' AND indexname = 'ix_ef_s3_config_uuid'
            ) THEN
                CREATE INDEX ix_ef_s3_config_uuid
                    ON encounter_files(s3_config_id, uuid);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'encounter_files' AND indexname = 'ix_ef_hospital_id'
            ) THEN
                CREATE INDEX ix_ef_hospital_id
                    ON encounter_files(hospital_id);
            END IF;
        END $$;
    """))

    # ========================================================================
    # 4. Add S3 columns to encounter_file_pdfs
    # ========================================================================
    conn.execute(text("""
        DO $$
        BEGIN
            -- hospital_id
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'encounter_file_pdfs' AND column_name = 'hospital_id'
            ) THEN
                ALTER TABLE encounter_file_pdfs
                ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id);

                CREATE INDEX ix_encounter_file_pdfs_hospital_id
                    ON encounter_file_pdfs(hospital_id);
            END IF;

            -- s3_config_id
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'encounter_file_pdfs' AND column_name = 's3_config_id'
            ) THEN
                ALTER TABLE encounter_file_pdfs
                ADD COLUMN s3_config_id INTEGER REFERENCES s3_configs(id);

                CREATE INDEX ix_encounter_file_pdfs_s3_config_id
                    ON encounter_file_pdfs(s3_config_id);
            END IF;

            -- s3_object_key
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'encounter_file_pdfs' AND column_name = 's3_object_key'
            ) THEN
                ALTER TABLE encounter_file_pdfs
                ADD COLUMN s3_object_key VARCHAR(500);
            END IF;

            -- Composite indexes for S3 queries
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'encounter_file_pdfs' AND indexname = 'ix_efpdf_s3_config_uuid'
            ) THEN
                CREATE INDEX ix_efpdf_s3_config_uuid
                    ON encounter_file_pdfs(s3_config_id, uuid);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'encounter_file_pdfs' AND indexname = 'ix_efpdf_hospital_id'
            ) THEN
                CREATE INDEX ix_efpdf_hospital_id
                    ON encounter_file_pdfs(hospital_id);
            END IF;
        END $$;
    """))


def downgrade() -> None:
    """
    Remove S3 storage support.

    NOTE: This will fail if there are existing S3 files (foreign key constraints).
    In production, you should migrate files back to local before downgrading.
    """
    conn = op.get_bind()

    # Drop indexes and columns from direct_image_uploads
    conn.execute(text("""
        DO $$
        BEGIN
            DROP INDEX IF EXISTS ix_diu_s3_config_created;
            DROP INDEX IF EXISTS ix_diu_s3_config_uuid;
            DROP INDEX IF EXISTS ix_direct_image_uploads_s3_config_id;
            DROP INDEX IF EXISTS ix_diu_hospital_id;

            ALTER TABLE direct_image_uploads DROP COLUMN IF EXISTS s3_object_key_edited_thumbnail;
            ALTER TABLE direct_image_uploads DROP COLUMN IF EXISTS s3_object_key_thumbnail;
            ALTER TABLE direct_image_uploads DROP COLUMN IF EXISTS s3_object_key_edited;
            ALTER TABLE direct_image_uploads DROP COLUMN IF EXISTS s3_object_key;
            ALTER TABLE direct_image_uploads DROP COLUMN IF EXISTS s3_config_id;
        END $$;
    """))

    # Drop indexes and columns from encounter_files
    conn.execute(text("""
        DO $$
        BEGIN
            DROP INDEX IF EXISTS ix_ef_s3_config_uuid;
            DROP INDEX IF EXISTS ix_encounter_files_s3_config_id;
            DROP INDEX IF EXISTS ix_ef_hospital_id;
            DROP INDEX IF EXISTS ix_encounter_files_hospital_id;

            ALTER TABLE encounter_files DROP COLUMN IF EXISTS s3_object_key_thumbnail;
            ALTER TABLE encounter_files DROP COLUMN IF EXISTS s3_object_key;
            ALTER TABLE encounter_files DROP COLUMN IF EXISTS s3_config_id;
            ALTER TABLE encounter_files DROP COLUMN IF EXISTS hospital_id;
        END $$;
    """))

    # Drop indexes and columns from encounter_file_pdfs
    conn.execute(text("""
        DO $$
        BEGIN
            DROP INDEX IF EXISTS ix_efpdf_s3_config_uuid;
            DROP INDEX IF EXISTS ix_encounter_file_pdfs_s3_config_id;
            DROP INDEX IF EXISTS ix_efpdf_hospital_id;
            DROP INDEX IF EXISTS ix_encounter_file_pdfs_hospital_id;

            ALTER TABLE encounter_file_pdfs DROP COLUMN IF EXISTS s3_object_key;
            ALTER TABLE encounter_file_pdfs DROP COLUMN IF EXISTS s3_config_id;
            ALTER TABLE encounter_file_pdfs DROP COLUMN IF EXISTS hospital_id;
        END $$;
    """))

    # Drop s3_configs table
    conn.execute(text("""
        DROP TABLE IF EXISTS s3_configs CASCADE;
    """))
