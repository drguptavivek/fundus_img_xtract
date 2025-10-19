-- Development migration for SQLite: Ad-hoc Task Creator support
-- 1) Create ad_hoc_task_creations table
CREATE TABLE IF NOT EXISTS ad_hoc_task_creations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_by_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  diseases_json TEXT NOT NULL,
  max_images INTEGER NOT NULL,
  filters_json TEXT NOT NULL,
  selected_image_refs_json TEXT NOT NULL,
  summary_json TEXT,
  FOREIGN KEY(created_by_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ad_hoc_task_creations_created_by ON ad_hoc_task_creations(created_by_id);
CREATE INDEX IF NOT EXISTS ix_ad_hoc_task_creations_created_at ON ad_hoc_task_creations(created_at);

-- 2) Add ad_hoc_id to grading_tasks (nullable)
ALTER TABLE grading_tasks ADD COLUMN ad_hoc_id INTEGER REFERENCES ad_hoc_task_creations(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_grading_tasks_ad_hoc_id ON grading_tasks(ad_hoc_id);

-- 3) Add randomized flag to ad_hoc_task_creations (nullable boolean)
ALTER TABLE ad_hoc_task_creations ADD COLUMN randomized BOOLEAN;
ALTER TABLE ad_hoc_task_creations ADD COLUMN remarks TEXT;

-- Note: SQLite cannot easily add CHECK constraints retrospectively; we rely on app-level validation.
