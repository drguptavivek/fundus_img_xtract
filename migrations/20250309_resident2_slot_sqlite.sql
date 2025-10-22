PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

-- Update existing data to use the resident2 nomenclature.
UPDATE grades SET role_slot = 'resident2' WHERE role_slot = 'faculty';
UPDATE grading_tasks SET state = 'resident2_done' WHERE state = 'faculty_done';
UPDATE task_tracker SET role_slot = 'resident2' WHERE role_slot = 'faculty';
UPDATE jobs SET upload_type = 'resident2 excel' WHERE upload_type = 'faculty excel';
UPDATE jobs SET rejected_summary = REPLACE(rejected_summary, 'Faculty', 'Resident2') WHERE rejected_summary LIKE '%Faculty%';

-- Rebuild grading_tasks to refresh the state constraint.
ALTER TABLE grading_tasks RENAME TO grading_tasks_old;
CREATE TABLE grading_tasks (
    id INTEGER NOT NULL,
    encounter_file_id INTEGER,
    direct_image_upload_id INTEGER,
    disease_id INTEGER NOT NULL,
    lab_unit_id INTEGER NOT NULL,
    state VARCHAR(24) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    ad_hoc_id INTEGER REFERENCES ad_hoc_task_creations(id) ON DELETE SET NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_grading_task_either_encounter_or_direct CHECK (
        (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR
        (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)
    ),
    CONSTRAINT uq_task_encounter_disease UNIQUE (encounter_file_id, disease_id),
    CONSTRAINT uq_task_direct_disease UNIQUE (direct_image_upload_id, disease_id),
    CONSTRAINT ck_task_state_valid CHECK (state IN ('pending','resident_done','resident2_done','arbitration','final')),
    FOREIGN KEY(encounter_file_id) REFERENCES encounter_files(id),
    FOREIGN KEY(direct_image_upload_id) REFERENCES direct_image_uploads(id),
    FOREIGN KEY(disease_id) REFERENCES diseases(id),
    FOREIGN KEY(lab_unit_id) REFERENCES lab_units(id)
);
INSERT INTO grading_tasks (
    id,
    encounter_file_id,
    direct_image_upload_id,
    disease_id,
    lab_unit_id,
    state,
    created_at,
    updated_at,
    ad_hoc_id
)
SELECT
    id,
    encounter_file_id,
    direct_image_upload_id,
    disease_id,
    lab_unit_id,
    state,
    created_at,
    updated_at,
    ad_hoc_id
FROM grading_tasks_old;
DROP TABLE grading_tasks_old;
CREATE INDEX ix_grading_tasks_disease_id ON grading_tasks (disease_id);
CREATE INDEX ix_grading_tasks_direct_image_upload_id ON grading_tasks (direct_image_upload_id);
CREATE INDEX ix_grading_tasks_encounter_file_id ON grading_tasks (encounter_file_id);
CREATE INDEX ix_grading_tasks_state ON grading_tasks (state);
CREATE INDEX ix_grading_tasks_lab_unit_id ON grading_tasks (lab_unit_id);
CREATE INDEX ix_task_disease_lab_state ON grading_tasks (disease_id, lab_unit_id, state);
CREATE INDEX ix_grading_tasks_ad_hoc_id ON grading_tasks(ad_hoc_id);

-- Rebuild grades to update the role_slot constraint.
ALTER TABLE grades RENAME TO grades_old;
CREATE TABLE grades (
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
    ai_model_name TEXT,
    ai_model_version TEXT,
    FOREIGN KEY(task_id) REFERENCES grading_tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(grader_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(disease_grading_id) REFERENCES disease_gradings(id),
    FOREIGN KEY(ai_model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    CHECK (role_slot IN ('resident','resident2','arbitrator','ai','review'))
);
INSERT INTO grades (
    id,
    task_id,
    grader_user_id,
    role_slot,
    disease_grading_id,
    comment,
    time_taken,
    start_time,
    created_at,
    updated_at,
    disease_name,
    grade_name,
    grade_description,
    ai_model_id,
    ai_model_name,
    ai_model_version
)
SELECT
    id,
    task_id,
    grader_user_id,
    role_slot,
    disease_grading_id,
    comment,
    time_taken,
    start_time,
    created_at,
    updated_at,
    disease_name,
    grade_name,
    grade_description,
    ai_model_id,
    ai_model_name,
    ai_model_version
FROM grades_old;
DROP TABLE grades_old;
CREATE INDEX ix_grades_task_slot ON grades (task_id, role_slot);
CREATE INDEX ix_grades_user_slot ON grades (grader_user_id, role_slot);
CREATE UNIQUE INDEX uq_grades_task_user_slot ON grades (task_id, grader_user_id, role_slot);
CREATE INDEX ix_grades_ai_model_id ON grades (ai_model_id);

-- Rebuild user_disease_unit_role to rename can_grade_faculty -> can_grade_resident2.
ALTER TABLE user_disease_unit_role RENAME TO user_disease_unit_role_old;
CREATE TABLE user_disease_unit_role (
    id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    disease_id INTEGER NOT NULL,
    lab_unit_id INTEGER NOT NULL,
    can_grade_resident BOOLEAN NOT NULL,
    can_grade_resident2 BOOLEAN NOT NULL,
    can_arbitrate BOOLEAN NOT NULL,
    active BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_user_disease_unit_role UNIQUE (user_id, disease_id, lab_unit_id),
    CONSTRAINT ck_user_dur_has_any_permission CHECK (
        (can_grade_resident = 1) OR (can_grade_resident2 = 1) OR (can_arbitrate = 1)
    ),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY(disease_id) REFERENCES diseases (id) ON DELETE CASCADE,
    FOREIGN KEY(lab_unit_id) REFERENCES lab_units (id) ON DELETE CASCADE
);
INSERT INTO user_disease_unit_role (
    id,
    user_id,
    disease_id,
    lab_unit_id,
    can_grade_resident,
    can_grade_resident2,
    can_arbitrate,
    active,
    created_at
)
SELECT
    id,
    user_id,
    disease_id,
    lab_unit_id,
    can_grade_resident,
    can_grade_faculty,
    can_arbitrate,
    active,
    created_at
FROM user_disease_unit_role_old;
DROP TABLE user_disease_unit_role_old;
CREATE INDEX ix_user_disease_unit_role_disease_id ON user_disease_unit_role (disease_id);
CREATE INDEX ix_user_dur_unit_disease ON user_disease_unit_role (lab_unit_id, disease_id);
CREATE INDEX ix_user_disease_unit_role_lab_unit_id ON user_disease_unit_role (lab_unit_id);
CREATE INDEX ix_user_disease_unit_role_user_id ON user_disease_unit_role (user_id);
CREATE INDEX ix_user_dur_user_active ON user_disease_unit_role (user_id, active);

COMMIT;
PRAGMA foreign_keys=on;
