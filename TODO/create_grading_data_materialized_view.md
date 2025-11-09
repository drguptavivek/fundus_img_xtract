# TODO: Create PostgreSQL Materialized View for Grading Data Analytics

## Overview
Create a comprehensive PostgreSQL **materialized view** with proper Alembic migration and indexes to consolidate all grade-related data including consensus grades for both direct and encounter file images.

## Implementation Steps

### 1. Create Alembic Migration File
- [ ] Generate new migration using `uv run alembic revision -autogenerate -m "create_grading_data_materialized_view"`
- [ ] This will create the migration file skeleton in `migrations/versions/`

### 2. Update Migration File with SQL Code
- [ ] **In the `upgrade()` function:**
  - [ ] Create materialized view `mvw_grading_data_all`
  - [ ] Include all JOINs for both image sources (DirectImageUpload & EncounterFile)
  - [ ] Add individual grades (resident, resident2, AI, arbitrator)
  - [ ] Add complete consensus grade information
  - [ ] Use COALESCE/CASE statements to handle dual image sources
  - [ ] Create indexes on the materialized view

- [ ] **In the `downgrade()` function:**
  - [ ] Drop the materialized view: `DROP MATERIALIZED VIEW IF EXISTS mvw_grading_data_all`

### 3. Materialized View Structure (Complete with Consensus)
```sql
CREATE MATERIALIZED VIEW mvw_grading_data_all AS
SELECT
    -- Image Metadata (unified from both sources)
    CASE
        WHEN ef.id IS NOT NULL THEN 'encounter_file'
        WHEN diu.id IS NOT NULL THEN 'direct_upload'
        ELSE 'unknown'
    END as image_source,
    COALESCE(ef.id, diu.id) as image_id,
    COALESCE(ef.uuid, diu.uuid) as image_uuid,
    COALESCE(ef.filename, diu.filename) as filename,
    COALESCE(ef.eye_side, diu.eye_side) as eye_side,

    -- Context Data
    ef.patient_encounter_id as patient_encounter_id,
    h.name as hospital_name,
    cam.name as camera_name,
    lu.name as lab_unit_name,

    -- Task Information
    gt.id as task_id,
    gt.uuid as task_uuid,
    gt.disease_id,
    d.name as disease_name,
    gt.state as task_state,
    gt.created_at as task_created_at,

    -- Individual Grade Details
    g.id as grade_id,
    g.role_slot as grade_role_slot,
    g.grader_user_id,
    grader.username as grader_username,
    dg.impression as grade_name,
    dg.guidelines as grade_description,
    g.comment as grade_comment,
    g.time_taken as grade_time_taken,
    g.created_at as grade_created_at,

    -- AI Model Information
    g.ai_model_id,
    ai.name as ai_model_name,

    -- **Complete Consensus Information**
    c.id as consensus_id,
    c.method as consensus_method,
    c.final_disease_grading_id as consensus_final_grade_id,
    consensus_dg.impression as consensus_final_grade_name,
    consensus_dg.guidelines as consensus_final_grade_description,
    c.decided_by_user_id as consensus_decided_by_user_id,
    decider.username as consensus_decider_name,
    c.created_at as consensus_created_at

FROM grading_tasks gt
-- Image source handling
LEFT JOIN encounter_files ef ON gt.encounter_file_id = ef.id
LEFT JOIN direct_image_uploads diu ON gt.direct_image_upload_id = diu.id

-- Core grading relationships
LEFT JOIN grades g ON gt.id = g.task_id
LEFT JOIN consensus c ON gt.id = c.task_id

-- Reference data joins
LEFT JOIN diseases d ON gt.disease_id = d.id
LEFT JOIN disease_gradings dg ON g.disease_grading_id = dg.id
LEFT JOIN disease_gradings consensus_dg ON c.final_disease_grading_id = consensus_dg.id
LEFT JOIN users grader ON g.grader_user_id = grader.id
LEFT JOIN users decider ON c.decided_by_user_id = decider.id
LEFT JOIN ai_models ai ON g.ai_model_id = ai.id

-- Contextual data joins
LEFT JOIN lab_units lu ON gt.lab_unit_id = lu.id
LEFT JOIN hospitals h ON diu.hospital_id = h.id
LEFT JOIN cameras cam ON diu.camera_id = cam.id;
```

### 4. Create Performance Indexes on Materialized View
- [ ] Image-related indexes:
  ```sql
  CREATE INDEX idx_mvw_grading_image_uuid ON mvw_grading_data_all(image_uuid);
  CREATE INDEX idx_mvw_grading_image_source ON mvw_grading_data_all(image_source);
  CREATE INDEX idx_mvw_grading_image_id ON mvw_grading_data_all(image_id);
  ```

- [ ] Grade-related indexes:
  ```sql
  CREATE INDEX idx_mvw_grading_task_id ON mvw_grading_data_all(task_id);
  CREATE INDEX idx_mvw_grading_grade_id ON mvw_grading_data_all(grade_id);
  CREATE INDEX idx_mvw_grading_grader_user ON mvw_grading_data_all(grader_user_id);
  CREATE INDEX idx_mvw_grading_role_slot ON mvw_grading_data_all(grade_role_slot);
  CREATE INDEX idx_mvw_grading_disease ON mvw_grading_data_all(disease_id);
  ```

- [ ] Time-based indexes:
  ```sql
  CREATE INDEX idx_mvw_grading_task_created ON mvw_grading_data_all(task_created_at);
  CREATE INDEX idx_mvw_grading_grade_created ON mvw_grading_data_all(grade_created_at);
  CREATE INDEX idx_mvw_grading_consensus_date ON mvw_grading_data_all(consensus_created_at);
  ```

- [ ] Consensus-specific indexes:
  ```sql
  CREATE INDEX idx_mvw_grading_consensus_id ON mvw_grading_data_all(consensus_id);
  CREATE INDEX idx_mvw_grading_consensus_method ON mvw_grading_data_all(consensus_method);
  ```

### 5. Refresh Strategy
- [ ] Add refresh function for automated updates:
  ```sql
  CREATE OR REPLACE FUNCTION refresh_grading_data_view()
  RETURNS void AS $$
  BEGIN
      REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_grading_data_all;
  END;
  $$ LANGUAGE plpgsql;
  ```

### 6. Test & Validate
- [ ] Run the migration: `uv run alembic upgrade head`
- [ ] Test materialized view queries with sample data
- [ ] Verify index creation and performance improvements
- [ ] Test refresh functionality: `SELECT refresh_grading_data_view();`
- [ ] Test rollback: `uv run alembic downgrade -1`

## Files to Create/Modify
- [ ] **Migration file**: `migrations/versions/[timestamp]_create_grading_data_materialized_view.py`
  - [ ] Generated via alembic command
  - [ ] Updated with comprehensive materialized view SQL
  - [ ] Includes index creation statements
  - [ ] Includes refresh function

## Advantages of Materialized View
- **Better Performance**: Pre-computed complex JOINs
- **Faster Analytics**: Ideal for reporting and data analysis
- **Reduced Load**: Less strain on database during complex queries
- **Concurrent Refreshes**: Can refresh without blocking reads

## Expected Outcome
- [ ] High-performance materialized view with all grade and consensus data
- [ ] Optimized for analytics and reporting workloads
- [ ] Properly indexed for fast query performance
- [ ] Automated refresh capability for data freshness

## Dependencies
- [ ] Database models: Grade, GradingTask, Consensus, DirectImageUpload, EncounterFile
- [ ] Reference tables: diseases, disease_gradings, users, ai_models, hospitals, cameras, lab_units

## Notes
- This view will be used for general purpose analytics and reporting
- Includes all historical data as requested
- Materialized view provides better performance than regular view for complex analytics queries
- Consider setting up automated refresh schedule (e.g., daily or hourly) depending on data freshness requirements