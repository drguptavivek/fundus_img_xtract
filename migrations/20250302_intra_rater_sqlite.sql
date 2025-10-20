-- SQLite migration for intra-rater reliability workflow

BEGIN TRANSACTION;

-- 0. Ensure app_settings table exists for global configuration storage
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL DEFAULT 'string',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Seed default cooldown (21 days) if not already present
INSERT OR IGNORE INTO app_settings (key, value, value_type, created_at, updated_at)
VALUES (
    'INTRA_RATER_DEFAULT_COOLDOWN_DAYS',
    '21',
    'integer',
    datetime('now'),
    datetime('now')
);

-- 1. Batches table capturing creation metadata
CREATE TABLE IF NOT EXISTS intra_rater_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    disease_id INTEGER NOT NULL,
    lab_unit_id INTEGER,
    created_by_user_id INTEGER,
    cooldown_days_override INTEGER,
    target_images_per_grader INTEGER NOT NULL,
    normal_grade_id INTEGER,
    selection_snapshot_json TEXT NOT NULL,
    remarks TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(disease_id) REFERENCES diseases(id),
    FOREIGN KEY(lab_unit_id) REFERENCES lab_units(id),
    FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY(normal_grade_id) REFERENCES disease_gradings(id)
);

CREATE INDEX IF NOT EXISTS ix_intra_rater_batches_disease ON intra_rater_batches(disease_id);
CREATE INDEX IF NOT EXISTS ix_intra_rater_batches_created_at ON intra_rater_batches(created_at);
CREATE INDEX IF NOT EXISTS ix_intra_rater_batches_normal_grade ON intra_rater_batches(normal_grade_id);

-- 2. Tasks table referencing source images/tasks
CREATE TABLE IF NOT EXISTS intra_rater_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    grader_user_id INTEGER NOT NULL,
    disease_id INTEGER NOT NULL,
    lab_unit_id INTEGER NOT NULL,
    encounter_file_id INTEGER,
    direct_image_upload_id INTEGER,
    source_task_id INTEGER,
    state TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(batch_id) REFERENCES intra_rater_batches(id) ON DELETE CASCADE,
    FOREIGN KEY(grader_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(disease_id) REFERENCES diseases(id),
    FOREIGN KEY(lab_unit_id) REFERENCES lab_units(id),
    FOREIGN KEY(encounter_file_id) REFERENCES encounter_files(id),
    FOREIGN KEY(direct_image_upload_id) REFERENCES direct_image_uploads(id),
    FOREIGN KEY(source_task_id) REFERENCES grading_tasks(id),
    CHECK (
        (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL)
        OR (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)
    ),
    CHECK (state IN ('pending','completed'))
);

CREATE INDEX IF NOT EXISTS ix_intra_rater_tasks_batch ON intra_rater_tasks(batch_id);
CREATE INDEX IF NOT EXISTS ix_intra_rater_tasks_grader_state ON intra_rater_tasks(grader_user_id, state);
CREATE INDEX IF NOT EXISTS ix_intra_rater_tasks_source_task ON intra_rater_tasks(source_task_id);
CREATE INDEX IF NOT EXISTS ix_intra_rater_tasks_disease_lab ON intra_rater_tasks(disease_id, lab_unit_id);

-- 3. Grades table capturing intra-rater submissions
CREATE TABLE IF NOT EXISTS intra_rater_grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    batch_id INTEGER NOT NULL,
    grader_user_id INTEGER NOT NULL,
    disease_grading_id INTEGER NOT NULL,
    comment TEXT,
    time_taken REAL,
    start_time TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    disease_name TEXT,
    grade_name TEXT,
    grade_description TEXT,
    FOREIGN KEY(task_id) REFERENCES intra_rater_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(batch_id) REFERENCES intra_rater_batches(id) ON DELETE CASCADE,
    FOREIGN KEY(grader_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(disease_grading_id) REFERENCES disease_gradings(id)
);

CREATE INDEX IF NOT EXISTS ix_intra_rater_grades_task ON intra_rater_grades(task_id);
CREATE INDEX IF NOT EXISTS ix_intra_rater_grades_batch ON intra_rater_grades(batch_id);
CREATE INDEX IF NOT EXISTS ix_intra_rater_grades_grader ON intra_rater_grades(grader_user_id);

COMMIT;
