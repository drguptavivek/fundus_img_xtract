-- SQLite-compatible migration for pre-graded uploads and AI grades

BEGIN TRANSACTION;

-- 1. Add new columns to direct_image_uploads
ALTER TABLE direct_image_uploads ADD COLUMN original_filename TEXT;
ALTER TABLE direct_image_uploads ADD COLUMN content_hash TEXT;
ALTER TABLE direct_image_uploads ADD COLUMN is_pregraded INTEGER NOT NULL DEFAULT 0;

-- Backfill original_filename and content_hash
UPDATE direct_image_uploads
SET original_filename = filename
WHERE original_filename IS NULL;

UPDATE direct_image_uploads
SET content_hash = file_hash
WHERE content_hash IS NULL;

-- 2. Add helper indexes (SQLite does not support IF NOT EXISTS in CREATE INDEX before v3.8.0)
CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_content_hash
    ON direct_image_uploads (content_hash);

CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_is_pregraded
    ON direct_image_uploads (is_pregraded);

-- 3. Create ai_models master table
CREATE TABLE IF NOT EXISTS ai_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, version)
);

-- 4. Rebuild grades table to add ai_model_id and expanded role constraints

CREATE TABLE grades_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    grader_user_id INTEGER NOT NULL,
    role_slot TEXT NOT NULL,
    disease_grading_id INTEGER NOT NULL,
    comment TEXT,
    time_taken REAL,
    start_time TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    disease_name TEXT,
    grade_name TEXT,
    grade_description TEXT,
    ai_model_id INTEGER,
    FOREIGN KEY(task_id) REFERENCES grading_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(grader_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(disease_grading_id) REFERENCES disease_gradings(id),
    FOREIGN KEY(ai_model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    CHECK (role_slot IN ('resident','faculty','arbitrator','ai'))
);

INSERT INTO grades_new (
    id, task_id, grader_user_id, role_slot, disease_grading_id, comment, time_taken,
    start_time, created_at, updated_at, disease_name, grade_name, grade_description
)
SELECT
    id, task_id, grader_user_id, role_slot, disease_grading_id, comment, time_taken,
    start_time, created_at, updated_at, disease_name, grade_name, grade_description
FROM grades;

DROP TABLE grades;
ALTER TABLE grades_new RENAME TO grades;

CREATE INDEX ix_grades_task_slot ON grades (task_id, role_slot);
CREATE INDEX ix_grades_user_slot ON grades (grader_user_id, role_slot);
CREATE UNIQUE INDEX uq_grades_task_user_slot ON grades (task_id, grader_user_id, role_slot);
CREATE INDEX ix_grades_ai_model_id ON grades (ai_model_id);

COMMIT;
