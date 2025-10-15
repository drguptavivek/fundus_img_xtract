-- Pre-graded upload & AI grading schema updates
-- Applies to PostgreSQL (adjust syntax for other databases as needed).

BEGIN;

-- Direct image uploads adjustments
ALTER TABLE direct_image_uploads
    ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255),
    ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32),
    ADD COLUMN IF NOT EXISTS is_pregraded BOOLEAN NOT NULL DEFAULT FALSE;

-- Ensure existing rows have default metadata
UPDATE direct_image_uploads
SET original_filename = filename
WHERE original_filename IS NULL;

UPDATE direct_image_uploads
SET content_hash = file_hash
WHERE content_hash IS NULL;

-- Drop unique constraint/index on file_hash to allow duplicate binaries
ALTER TABLE direct_image_uploads
    DROP CONSTRAINT IF EXISTS direct_image_uploads_file_hash_key;

DROP INDEX IF EXISTS ix_direct_image_uploads_file_hash;

-- Recreate a non-unique index for fast lookup
CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_content_hash
    ON direct_image_uploads (content_hash);

CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_is_pregraded
    ON direct_image_uploads (is_pregraded);

-- AI model master
CREATE TABLE IF NOT EXISTS ai_models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    version VARCHAR(64) NOT NULL,
    description TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ai_models_name_version UNIQUE (name, version)
);

-- Grades table enhancements
ALTER TABLE grades
    ADD COLUMN IF NOT EXISTS ai_model_id INTEGER NULL,
    ADD CONSTRAINT fk_grades_ai_model
        FOREIGN KEY (ai_model_id) REFERENCES ai_models (id) ON DELETE SET NULL;

-- Relax role slot constraint to allow AI grades
ALTER TABLE grades
    DROP CONSTRAINT IF EXISTS ck_grade_role_slot_valid;

ALTER TABLE grades
    ADD CONSTRAINT ck_grade_role_slot_valid
        CHECK (role_slot IN ('resident','faculty','arbitrator','ai'));

CREATE INDEX IF NOT EXISTS ix_grades_ai_model_id ON grades (ai_model_id);

COMMIT;
