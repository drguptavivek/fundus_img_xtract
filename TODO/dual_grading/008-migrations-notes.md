# Migration Notes — Dual Grading Schema - DONE and FIXED

This outlines the migration steps to introduce grading tasks, grades, consensus, eligibility, and (optionally) AI grades. Keep migrations small and reversible. Update `scripts/setup_db.py` and `scripts/migrations.md` accordingly.

General Guidance
- SQLite friendly: avoid advanced partial indexes. Use CHECK constraints and separate UNIQUE constraints as shown.
- Idempotent: use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` where issuing raw SQL.
- Do not drop legacy tables (`image_gradings`) during initial rollout.

Tables to Create
- `grading_tasks`
- `grades`
- `consensus`
- `user_disease_unit_role`
- `ai_grades` (optional)

DDL Sketch (SQLite)
- Either issue through SQLAlchemy metadata (preferred) by adding models and calling `Base.metadata.create_all(engine)` for new tables only, or use raw SQL with guards.

Example Raw SQL Blocks (SQLite)
- grading_tasks

```sql
CREATE TABLE IF NOT EXISTS grading_tasks (
  id INTEGER PRIMARY KEY,
  encounter_file_id INTEGER NULL,
  direct_image_upload_id INTEGER NULL,
  disease_id INTEGER NOT NULL,
  lab_unit_id INTEGER NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_grading_task_either_encounter_or_direct CHECK (
    (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR
    (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)
  ),
  CONSTRAINT uq_task_encounter_disease UNIQUE (encounter_file_id, disease_id),
  CONSTRAINT uq_task_direct_disease UNIQUE (direct_image_upload_id, disease_id),
  CONSTRAINT ck_task_state_valid CHECK (state IN ('pending','resident_done','faculty_done','arbitration','final'))
);
CREATE INDEX IF NOT EXISTS ix_task_encounter ON grading_tasks(encounter_file_id);
CREATE INDEX IF NOT EXISTS ix_task_direct ON grading_tasks(direct_image_upload_id);
CREATE INDEX IF NOT EXISTS ix_task_disease_lab_state ON grading_tasks(disease_id, lab_unit_id, state);
```

Global Uniqueness & Gold Standard
- The pair `(encounter_file_id, disease_id)` and `(direct_image_upload_id, disease_id)` are each unique, enforcing one task per image×disease globally. `lab_unit_id` scopes assignment/queues only.
- Once a task reaches `state='final'` (via match or adjudication), treat it as the gold standard for that image×disease across all labs; do not allow creation of another task for the same image×disease.

Operational Guardrails (Service Layer)
- `create_or_get_task(...)` must first search for an existing image×disease task; if found, return it as‑is and never mutate `lab_unit_id`.
- `ensure_task(image_uuid, disease_id)` derives the lab from the image and applies verification gating; if an existing task is final, return a 409-style error to callers indicating cross‑lab reassignment is disabled after final consensus.

- grades

```sql
CREATE TABLE IF NOT EXISTS grades (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  grader_user_id INTEGER NOT NULL,
  role_slot TEXT NOT NULL,
  disease_grading_id INTEGER NOT NULL,
  comment TEXT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_grade_role_slot_valid CHECK (role_slot IN ('resident','faculty','arbitrator'))
);
CREATE INDEX IF NOT EXISTS ix_grade_task ON grades(task_id);
CREATE INDEX IF NOT EXISTS ix_grade_user ON grades(grader_user_id);
CREATE INDEX IF NOT EXISTS ix_grade_task_slot ON grades(task_id, role_slot);
CREATE INDEX IF NOT EXISTS ix_grade_user_slot ON grades(grader_user_id, role_slot);
```

- consensus

```sql
CREATE TABLE IF NOT EXISTS consensus (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL UNIQUE,
  final_disease_grading_id INTEGER NOT NULL,
  method TEXT NOT NULL,
  decided_by_user_id INTEGER NULL,
  decided_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_consensus_method_valid CHECK (method IN ('match','adjudication'))
);
CREATE INDEX IF NOT EXISTS ix_consensus_method ON consensus(method);
```

- user_disease_unit_role

```sql
CREATE TABLE IF NOT EXISTS user_disease_unit_role (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  disease_id INTEGER NOT NULL,
  lab_unit_id INTEGER NOT NULL,
  can_grade_resident BOOLEAN NOT NULL DEFAULT 0,
  can_grade_faculty BOOLEAN NOT NULL DEFAULT 0,
  can_arbitrate BOOLEAN NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_user_disease_unit_role UNIQUE (user_id, disease_id, lab_unit_id),
  CONSTRAINT ck_user_dur_has_any_permission CHECK (
    can_grade_resident = 1 OR can_grade_faculty = 1 OR can_arbitrate = 1
  )
);
CREATE INDEX IF NOT EXISTS ix_user_dur_unit_disease ON user_disease_unit_role(lab_unit_id, disease_id);
CREATE INDEX IF NOT EXISTS ix_user_dur_user_active ON user_disease_unit_role(user_id, active);
```

- ai_grades (optional)

```sql
CREATE TABLE IF NOT EXISTS ai_grades (
  id INTEGER PRIMARY KEY,
  encounter_file_id INTEGER NULL,
  direct_image_upload_id INTEGER NULL,
  disease_id INTEGER NOT NULL,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  label_disease_grading_id INTEGER NULL,
  confidence REAL NULL,
  probabilities_json TEXT NULL,
  run_id TEXT NULL,
  inference_time_ms INTEGER NULL,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT ck_ai_grade_either_encounter_or_direct CHECK (
    (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR
    (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_encounter_model_run ON ai_grades(encounter_file_id, disease_id, model_name, model_version, run_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_direct_model_run ON ai_grades(direct_image_upload_id, disease_id, model_name, model_version, run_id);
```




Backfill/Auto-Create Hooks
- Direct verify: in `preprocess/anonymize_image.py` after setting verified, call a service to `create_or_get_task` for the image’s native `disease_id`.
- DR verify: in `verify_remedio_dr/routes.py` after `dr_verified_status='verified'`, iterate related images and create tasks for DR.
- Glaucoma verify: in `glaucoma/routes.py` after `glaucoma_verified_status='verified'`, iterate related images and create tasks for Glaucoma.

Testing the Migration
- After running the migration flag, confirm tables exist: 

Notes
- Keep legacy `image_gradings` table for history during transition; do not delete or mutate it yet.
- Ensure all foreign keys use `ondelete='CASCADE'` where appropriate to avoid orphaned rows in dev (exercise caution in production).

