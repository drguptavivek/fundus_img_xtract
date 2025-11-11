# Create Comprehensive Encounter Pivot Materialized View

## Executive Summary

### Purpose
Create `mvw_encounter_pivot` materialized view to consolidate all encounter-level data into a single, optimized row per encounter with comprehensive individual image-grade pivots for all role types and diseases.

### Key Benefits
- **Encounter-Centric Analytics**: Single query for complete encounter analysis
- **Individual Image Tracking**: Detailed grade-by-grade analysis for each image
- **Comprehensive Disease Coverage**: DR, Glaucoma, AMD, plus ad-hoc disease support
- **Research Ready**: Perfect for clinical studies and quality assurance
- **Performance Optimized**: Strategic indexing for fast analytics queries

### Scope
- One row per PatientEncounter
- Complete coverage of all verification statuses and disease results
- Individual image-grade pivots with JSON structure
- All role types: resident, resident2, arbitrator, ai, review
- All diseases: Diabetic Retinopathy, Glaucoma, AMD, plus additional diseases

## Database Schema Analysis

### Core Table Relationships

#### PatientEncounters (Primary Entity)
```sql
-- Key Fields to Include:
pe.id                    -- Primary identifier
pe.name                 -- Encounter name
pe.patient_id           -- Patient identifier
pe.capture_date         -- String format
pe.capture_date_dt      -- Date format for queries
pe.encounter_verified_status    -- General verification
pe.glaucoma_verified_status     -- Glaucoma verification
pe.dr_verified_status           -- DR verification
pe.lab_unit_id          -- Organizational context
pe.created_at           -- Data freshness tracking
pe.updated_at           -- Last modification time
```

#### DiabeticRetinopathyReport (Complete Coverage)
```sql
-- Relationship: patient_encounter_id (1:many)
dr.id                   -- Report identifier
dr.uuid                 -- Report UUID
dr.result               -- DR result classification
dr.qualitative_result   -- Qualitative DR assessment
dr.report_file_name     -- Source document
dr.patient_encounter_id -- Foreign key to PatientEncounters
```

#### GlaucomaResultsCleaned (Complete Coverage)
```sql
-- Relationship: patient_encounter_id (1:1 for latest record)
grc.id                  -- Cleaned result identifier
grc.vcdr_right_num      -- Numeric right VCDR
grc.vcdr_left_num       -- Numeric left VCDR
grc.result              -- Glaucoma result classification
grc.qualitative_result  -- Qualitative glaucoma assessment
grc.report_uuid         -- Report UUID
grc.report_file_name    -- Source document
grc.updated_at          -- Result freshness
grc.patient_encounter_id -- Foreign key to PatientEncounters
```

#### Image Sources
```sql
-- EncounterFile (ZIP-based images)
ef.id                   -- Image identifier
ef.patient_encounter_id -- Foreign key to PatientEncounters
ef.uuid                 -- Image UUID for lookups
ef.eye_side             -- Left/Right eye designation
ef.file_type            -- Image format/type
ef.filename             -- Original filename

-- DirectImageUpload (via GradingTask linkage)
-- Note: Simplified counting - no complex joins needed
diu.id                  -- Direct upload identifier
diu.uuid                -- Direct upload UUID
diu.lab_unit_id         -- Organizational context
```

#### Grading System Structure
```sql
-- GradingTask (Central task entity)
gt.id                   -- Task identifier
gt.encounter_file_id    -- Link to encounter images
gt.direct_image_upload_id -- Link to direct uploads
gt.disease_id           -- Disease being graded
gt.lab_unit_id          -- Organizational context
gt.state                -- pending, resident_done, resident2_done, arbitration, final

-- Grade (Individual grades by role)
g.id                    -- Grade identifier
g.task_id               -- Link to GradingTask
g.grader_user_id        -- Grader information
g.role_slot             -- resident, resident2, arbitrator, ai, review
g.disease_grading_id    -- Grade classification
g.selected_features_json -- Feature selections
g.time_taken            -- Grading duration
g.created_at, g.updated_at -- Timestamps

-- Consensus (Final decisions)
c.id                    -- Consensus identifier
c.task_id               -- Link to GradingTask
c.final_disease_grading_id -- Final classification
c.method                -- match, adjudication
c.decided_by_user_id    -- Decision maker
c.decided_at            -- Decision timestamp
```

## Technical Specifications

### Complete SQL DDL

```sql
CREATE MATERIALIZED VIEW mvw_encounter_pivot AS
SELECT
  -- ==========================================
  -- CORE ENCOUNTER INFORMATION
  -- ==========================================
  pe.id as encounter_id,
  pe.name as encounter_name,
  pe.patient_id as patient_identifier,
  pe.capture_date as capture_date_str,
  pe.capture_date_dt as capture_date,

  -- ==========================================
  -- VERIFICATION STATUS (All Three Types)
  -- ==========================================
  pe.encounter_verified_status,
  pe.glaucoma_verified_status,
  pe.dr_verified_status,

  -- ==========================================
  -- CONTEXT INFORMATION
  -- ==========================================
  h.id as hospital_id,
  h.name as hospital_name,
  lu.id as lab_unit_id,
  lu.name as lab_unit_name,

  -- ==========================================
  -- IMAGE AGGREGATION (Simplified)
  -- ==========================================
  COUNT(DISTINCT ef.id) as total_images,
  COALESCE(json_agg(ef.uuid ORDER BY ef.id), '[]'::json) as image_uuids,
  COALESCE(json_agg(ef.eye_side ORDER BY ef.id), '[]'::json) as eye_sides,
  COALESCE(json_agg(ef.file_type ORDER BY ef.id), '[]'::json) as image_types,

  -- ==========================================
  -- DISEASE REPORTS (Complete Coverage)
  -- ==========================================
  -- Diabetic Retinopathy Reports
  dr.id as dr_report_id,
  dr.uuid as dr_report_uuid,
  dr.result as dr_result,
  dr.qualitative_result as dr_qualitative_result,
  dr.report_file_name as dr_report_file_name,

  -- Glaucoma Results Cleaned
  grc.id as glaucoma_cleaned_id,
  grc.vcdr_right_num as glaucoma_vcdr_right_num,
  grc.vcdr_left_num as glaucoma_vcdr_left_num,
  grc.result as glaucoma_result,
  grc.qualitative_result as glaucoma_qualitative_result,
  grc.report_uuid as glaucoma_report_uuid,
  grc.report_file_name as glaucoma_report_file_name,
  grc.updated_at as glaucoma_result_updated_at,

  -- ==========================================
  -- INDIVIDUAL IMAGE-GRADE PIVOTS (Key Feature)
  -- ==========================================
  -- Each image has complete grading data across all diseases and roles
  COALESCE(json_agg(
    CASE WHEN ef.id IS NOT NULL THEN
      json_build_object(
        'image_id', ef.id,
        'image_uuid', ef.uuid,
        'eye_side', ef.eye_side,
        'file_type', ef.file_type,

        -- ==========================================
        -- DIABETIC RETINOPATHY GRADES
        -- ==========================================
        'dr_resident_grade', COALESCE(dr_resident.impression, ''),
        'dr_resident_grade_id', COALESCE(dr_resident_g.id, 0),
        'dr_resident_grader', COALESCE(dr_resident_u.username, ''),
        'dr_resident_time', dr_resident_g.time_taken,
        'dr_resident_features', dr_resident_g.selected_features_json,

        'dr_resident2_grade', COALESCE(dr_resident2.impression, ''),
        'dr_resident2_grade_id', COALESCE(dr_resident2_g.id, 0),
        'dr_resident2_grader', COALESCE(dr_resident2_u.username, ''),
        'dr_resident2_time', dr_resident2_g.time_taken,
        'dr_resident2_features', dr_resident2_g.selected_features_json,

        'dr_arbitrator_grade', COALESCE(dr_arbitrator.impression, ''),
        'dr_arbitrator_grade_id', COALESCE(dr_arbitrator_g.id, 0),
        'dr_arbitrator_grader', COALESCE(dr_arbitrator_u.username, ''),
        'dr_arbitrator_time', dr_arbitrator_g.time_taken,
        'dr_arbitrator_features', dr_arbitrator_g.selected_features_json,

        'dr_ai_grade', COALESCE(dr_ai.impression, ''),
        'dr_ai_grade_id', COALESCE(dr_ai_g.id, 0),
        'dr_ai_model_name', dr_ai_g.ai_model_name,
        'dr_ai_model_version', dr_ai_g.ai_model_version,
        'dr_ai_confidence', dr_ai_g.ai_confidence,

        'dr_review_grade', COALESCE(dr_review.impression, ''),
        'dr_review_grade_id', COALESCE(dr_review_g.id, 0),
        'dr_review_grader', COALESCE(dr_review_u.username, ''),
        'dr_review_time', dr_review_g.time_taken,

        'dr_consensus_grade', COALESCE(dr_consensus.final_label.impression, ''),
        'dr_consensus_grade_id', COALESCE(dr_consensus.final_disease_grading_id, 0),
        'dr_consensus_method', COALESCE(dr_consensus.method, ''),
        'dr_consensus_decider', COALESCE(dr_consensus_decider_u.username, ''),
        'dr_consensus_decided_at', dr_consensus.decided_at,

        -- ==========================================
        -- GLAUCOMA GRADES
        -- ==========================================
        'glaucoma_resident_grade', COALESCE(glaucoma_resident.impression, ''),
        'glaucoma_resident_grade_id', COALESCE(glaucoma_resident_g.id, 0),
        'glaucoma_resident_grader', COALESCE(glaucoma_resident_u.username, ''),
        'glaucoma_resident_time', glaucoma_resident_g.time_taken,
        'glaucoma_resident_features', glaucoma_resident_g.selected_features_json,

        'glaucoma_resident2_grade', COALESCE(glaucoma_resident2.impression, ''),
        'glaucoma_resident2_grade_id', COALESCE(glaucoma_resident2_g.id, 0),
        'glaucoma_resident2_grader', COALESCE(glaucoma_resident2_u.username, ''),
        'glaucoma_resident2_time', glaucoma_resident2_g.time_taken,
        'glaucoma_resident2_features', glaucoma_resident2_g.selected_features_json,

        'glaucoma_arbitrator_grade', COALESCE(glaucoma_arbitrator.impression, ''),
        'glaucoma_arbitrator_grade_id', COALESCE(glaucoma_arbitrator_g.id, 0),
        'glaucoma_arbitrator_grader', COALESCE(glaucoma_arbitrator_u.username, ''),
        'glaucoma_arbitrator_time', glaucoma_arbitrator_g.time_taken,
        'glaucoma_arbitrator_features', glaucoma_arbitrator_g.selected_features_json,

        'glaucoma_ai_grade', COALESCE(glaucoma_ai.impression, ''),
        'glaucoma_ai_grade_id', COALESCE(glaucoma_ai_g.id, 0),
        'glaucoma_ai_model_name', glaucoma_ai_g.ai_model_name,
        'glaucoma_ai_model_version', glaucoma_ai_g.ai_model_version,
        'glaucoma_ai_confidence', glaucoma_ai_g.ai_confidence,

        'glaucoma_review_grade', COALESCE(glaucoma_review.impression, ''),
        'glaucoma_review_grade_id', COALESCE(glaucoma_review_g.id, 0),
        'glaucoma_review_grader', COALESCE(glaucoma_review_u.username, ''),
        'glaucoma_review_time', glaucoma_review_g.time_taken,

        'glaucoma_consensus_grade', COALESCE(glaucoma_consensus.final_label.impression, ''),
        'glaucoma_consensus_grade_id', COALESCE(glaucoma_consensus.final_disease_grading_id, 0),
        'glaucoma_consensus_method', COALESCE(glaucoma_consensus.method, ''),
        'glaucoma_consensus_decider', COALESCE(glaucoma_consensus_decider_u.username, ''),
        'glaucoma_consensus_decided_at', glaucoma_consensus.decided_at,

        -- ==========================================
        -- AMD GRADES (From Ad-Hoc Tasks)
        -- ==========================================
        'amd_resident_grade', COALESCE(amd_resident.impression, ''),
        'amd_resident_grade_id', COALESCE(amd_resident_g.id, 0),
        'amd_resident_grader', COALESCE(amd_resident_u.username, ''),
        'amd_resident_time', amd_resident_g.time_taken,
        'amd_resident_features', amd_resident_g.selected_features_json,

        'amd_resident2_grade', COALESCE(amd_resident2.impression, ''),
        'amd_resident2_grade_id', COALESCE(amd_resident2_g.id, 0),
        'amd_resident2_grader', COALESCE(amd_resident2_u.username, ''),
        'amd_resident2_time', amd_resident2_g.time_taken,
        'amd_resident2_features', amd_resident2_g.selected_features_json,

        'amd_arbitrator_grade', COALESCE(amd_arbitrator.impression, ''),
        'amd_arbitrator_grade_id', COALESCE(amd_arbitrator_g.id, 0),
        'amd_arbitrator_grader', COALESCE(amd_arbitrator_u.username, ''),
        'amd_arbitrator_time', amd_arbitrator_g.time_taken,
        'amd_arbitrator_features', amd_arbitrator_g.selected_features_json,

        'amd_ai_grade', COALESCE(amd_ai.impression, ''),
        'amd_ai_grade_id', COALESCE(amd_ai_g.id, 0),
        'amd_ai_model_name', amd_ai_g.ai_model_name,
        'amd_ai_model_version', amd_ai_g.ai_model_version,
        'amd_ai_confidence', amd_ai_g.ai_confidence,

        'amd_review_grade', COALESCE(amd_review.impression, ''),
        'amd_review_grade_id', COALESCE(amd_review_g.id, 0),
        'amd_review_grader', COALESCE(amd_review_u.username, ''),
        'amd_review_time', amd_review_g.time_taken,

        'amd_consensus_grade', COALESCE(amd_consensus.final_label.impression, ''),
        'amd_consensus_grade_id', COALESCE(amd_consensus.final_disease_grading_id, 0),
        'amd_consensus_method', COALESCE(amd_consensus.method, ''),
        'amd_consensus_decider', COALESCE(amd_consensus_decider_u.username, ''),
        'amd_consensus_decided_at', amd_consensus.decided_at,

        -- ==========================================
        -- ADDITIONAL DISEASES (Dynamic from Ad-Hoc Tasks)
        -- ==========================================
        'additional_diseases', COALESCE(
          json_agg(
            DISTINCT CASE
              WHEN d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD') THEN
                json_build_object(
                  'disease_name', d.name,
                  'disease_id', d.id,
                  'resident_grade', COALESCE(additional_resident.impression, ''),
                  'resident2_grade', COALESCE(additional_resident2.impression, ''),
                  'arbitrator_grade', COALESCE(additional_arbitrator.impression, ''),
                  'ai_grade', COALESCE(additional_ai.impression, ''),
                  'consensus_grade', COALESCE(additional_consensus.final_label.impression, '')
                )
            END
          ) FILTER (WHERE d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD') AND d.name IS NOT NULL),
          '[]'::json
        )
      )
    END
  ) FILTER (WHERE ef.id IS NOT NULL), '[]'::json) as image_grade_pivots,

  -- ==========================================
  -- TASK SUMMARY BY DISEASE
  -- ==========================================
  COUNT(DISTINCT CASE WHEN d.name = 'Diabetic Retinopathy' THEN gt.id END) as dr_task_count,
  COUNT(DISTINCT CASE WHEN d.name = 'Glaucoma' THEN gt.id END) as glaucoma_task_count,
  COUNT(DISTINCT CASE WHEN d.name = 'AMD' THEN gt.id END) as amd_task_count,
  COUNT(DISTINCT CASE WHEN d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD') THEN gt.id END) as additional_disease_task_count,
  COUNT(DISTINCT gt.id) as total_task_count,

  -- Task status breakdown
  COUNT(DISTINCT CASE WHEN gt.state = 'pending' THEN gt.id END) as pending_tasks,
  COUNT(DISTINCT CASE WHEN gt.state = 'resident_done' THEN gt.id END) as resident_done_tasks,
  COUNT(DISTINCT CASE WHEN gt.state = 'resident2_done' THEN gt.id END) as resident2_done_tasks,
  COUNT(DISTINCT CASE WHEN gt.state = 'arbitration' THEN gt.id END) as arbitration_tasks,
  COUNT(DISTINCT CASE WHEN gt.state = 'final' THEN gt.id END) as final_tasks,

  -- ==========================================
  -- TIME-BASED ANALYSIS
  -- ==========================================
  pe.created_at as encounter_created_at,
  pe.updated_at as encounter_updated_at,
  MAX(COALESCE(g.updated_at, gt.created_at)) as last_grading_activity,

  -- Data freshness metrics
  EXTRACT(EPOCH FROM (NOW() - pe.updated_at))/60 as data_freshness_minutes,
  EXTRACT(EPOCH FROM (NOW() - MAX(COALESCE(g.updated_at, gt.created_at))))/60 as grading_freshness_minutes

FROM patient_encounters pe
LEFT JOIN lab_units lu ON pe.lab_unit_id = lu.id
LEFT JOIN hospitals h ON lu.hospital_id = h.id
LEFT JOIN encounter_files ef ON pe.id = ef.patient_encounter_id

-- ==========================================
-- COMPREHENSIVE GRADING SYSTEM JOINS
-- ==========================================
LEFT JOIN grading_tasks gt ON ef.id = gt.encounter_file_id
LEFT JOIN diseases d ON gt.disease_id = d.id

-- Diabetic Retinopathy Grade Joins
LEFT JOIN grades dr_resident_g ON gt.id = dr_resident_g.task_id AND dr_resident_g.role_slot = 'resident' AND d.name = 'Diabetic Retinopathy'
LEFT JOIN disease_gradings dr_resident ON dr_resident_g.disease_grading_id = dr_resident.id
LEFT JOIN users dr_resident_u ON dr_resident_g.grader_user_id = dr_resident_u.id

LEFT JOIN grades dr_resident2_g ON gt.id = dr_resident2_g.task_id AND dr_resident2_g.role_slot = 'resident2' AND d.name = 'Diabetic Retinopathy'
LEFT JOIN disease_gradings dr_resident2 ON dr_resident2_g.disease_grading_id = dr_resident2.id
LEFT JOIN users dr_resident2_u ON dr_resident2_g.grader_user_id = dr_resident2_u.id

LEFT JOIN grades dr_arbitrator_g ON gt.id = dr_arbitrator_g.task_id AND dr_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'Diabetic Retinopathy'
LEFT JOIN disease_gradings dr_arbitrator ON dr_arbitrator_g.disease_grading_id = dr_arbitrator.id
LEFT JOIN users dr_arbitrator_u ON dr_arbitrator_g.grader_user_id = dr_arbitrator_u.id

LEFT JOIN grades dr_ai_g ON gt.id = dr_ai_g.task_id AND dr_ai_g.role_slot = 'ai' AND d.name = 'Diabetic Retinopathy'
LEFT JOIN disease_gradings dr_ai ON dr_ai_g.disease_grading_id = dr_ai.id

LEFT JOIN grades dr_review_g ON gt.id = dr_review_g.task_id AND dr_review_g.role_slot = 'review' AND d.name = 'Diabetic Retinopathy'
LEFT JOIN disease_gradings dr_review ON dr_review_g.disease_grading_id = dr_review.id
LEFT JOIN users dr_review_u ON dr_review_g.grader_user_id = dr_review_u.id

-- Glaucoma Grade Joins
LEFT JOIN grades glaucoma_resident_g ON gt.id = glaucoma_resident_g.task_id AND glaucoma_resident_g.role_slot = 'resident' AND d.name = 'Glaucoma'
LEFT JOIN disease_gradings glaucoma_resident ON glaucoma_resident_g.disease_grading_id = glaucoma_resident.id
LEFT JOIN users glaucoma_resident_u ON glaucoma_resident_g.grader_user_id = glaucoma_resident_u.id

LEFT JOIN grades glaucoma_resident2_g ON gt.id = glaucoma_resident2_g.task_id AND glaucoma_resident2_g.role_slot = 'resident2' AND d.name = 'Glaucoma'
LEFT JOIN disease_gradings glaucoma_resident2 ON glaucoma_resident2_g.disease_grading_id = glaucoma_resident2.id
LEFT JOIN users glaucoma_resident2_u ON glaucoma_resident2_g.grader_user_id = glaucoma_resident2_u.id

LEFT JOIN grades glaucoma_arbitrator_g ON gt.id = glaucoma_arbitrator_g.task_id AND glaucoma_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'Glaucoma'
LEFT JOIN disease_gradings glaucoma_arbitrator ON glaucoma_arbitrator_g.disease_grading_id = glaucoma_arbitrator.id
LEFT JOIN users glaucoma_arbitrator_u ON glaucoma_arbitrator_g.grader_user_id = glaucoma_arbitrator_u.id

LEFT JOIN grades glaucoma_ai_g ON gt.id = glaucoma_ai_g.task_id AND glaucoma_ai_g.role_slot = 'ai' AND d.name = 'Glaucoma'
LEFT JOIN disease_gradings glaucoma_ai ON glaucoma_ai_g.disease_grading_id = glaucoma_ai.id

LEFT JOIN grades glaucoma_review_g ON gt.id = glaucoma_review_g.task_id AND glaucoma_review_g.role_slot = 'review' AND d.name = 'Glaucoma'
LEFT JOIN disease_gradings glaucoma_review ON glaucoma_review_g.disease_grading_id = glaucoma_review.id
LEFT JOIN users glaucoma_review_u ON glaucoma_review_g.grader_user_id = glaucoma_review_u.id

-- AMD Grade Joins (From Ad-Hoc Tasks)
LEFT JOIN grades amd_resident_g ON gt.id = amd_resident_g.task_id AND amd_resident_g.role_slot = 'resident' AND d.name = 'AMD'
LEFT JOIN disease_gradings amd_resident ON amd_resident_g.disease_grading_id = amd_resident.id
LEFT JOIN users amd_resident_u ON amd_resident_g.grader_user_id = amd_resident_u.id

LEFT JOIN grades amd_resident2_g ON gt.id = amd_resident2_g.task_id AND amd_resident2_g.role_slot = 'resident2' AND d.name = 'AMD'
LEFT JOIN disease_gradings amd_resident2 ON amd_resident2_g.disease_grading_id = amd_resident2.id
LEFT JOIN users amd_resident2_u ON amd_resident2_g.grader_user_id = amd_resident2_u.id

LEFT JOIN grades amd_arbitrator_g ON gt.id = amd_arbitrator_g.task_id AND amd_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'AMD'
LEFT JOIN disease_gradings amd_arbitrator ON amd_arbitrator_g.disease_grading_id = amd_arbitrator.id
LEFT JOIN users amd_arbitrator_u ON amd_arbitrator_g.grader_user_id = amd_arbitrator_u.id

LEFT JOIN grades amd_ai_g ON gt.id = amd_ai_g.task_id AND amd_ai_g.role_slot = 'ai' AND d.name = 'AMD'
LEFT JOIN disease_gradings amd_ai ON amd_ai_g.disease_grading_id = amd_ai.id

LEFT JOIN grades amd_review_g ON gt.id = amd_review_g.task_id AND amd_review_g.role_slot = 'review' AND d.name = 'AMD'
LEFT JOIN disease_gradings amd_review ON amd_review_g.disease_grading_id = amd_review.id
LEFT JOIN users amd_review_u ON amd_review_g.grader_user_id = amd_review_u.id

-- Additional Diseases (Dynamic)
LEFT JOIN grades additional_resident_g ON gt.id = additional_resident_g.task_id AND additional_resident_g.role_slot = 'resident'
LEFT JOIN disease_gradings additional_resident ON additional_resident_g.disease_grading_id = additional_resident.id

LEFT JOIN grades additional_resident2_g ON gt.id = additional_resident2_g.task_id AND additional_resident2_g.role_slot = 'resident2'
LEFT JOIN disease_gradings additional_resident2 ON additional_resident2_g.disease_grading_id = additional_resident2.id

LEFT JOIN grades additional_arbitrator_g ON gt.id = additional_arbitrator_g.task_id AND additional_arbitrator_g.role_slot = 'arbitrator'
LEFT JOIN disease_gradings additional_arbitrator ON additional_arbitrator_g.disease_grading_id = additional_arbitrator.id

LEFT JOIN grades additional_ai_g ON gt.id = additional_ai_g.task_id AND additional_ai_g.role_slot = 'ai'
LEFT JOIN disease_gradings additional_ai ON additional_ai_g.disease_grading_id = additional_ai.id

-- ==========================================
-- CONSENSUS JOINS FOR EACH DISEASE
-- ==========================================
LEFT JOIN consensus dr_consensus ON gt.id = dr_consensus.task_id AND d.name = 'Diabetic Retinopathy'
LEFT JOIN disease_gradings dr_consensus_label ON dr_consensus.final_disease_grading_id = dr_consensus_label.id
LEFT JOIN users dr_consensus_decider_u ON dr_consensus.decided_by_user_id = dr_consensus_decider_u.id

LEFT JOIN consensus glaucoma_consensus ON gt.id = glaucoma_consensus.task_id AND d.name = 'Glaucoma'
LEFT JOIN disease_gradings glaucoma_consensus_label ON glaucoma_consensus.final_disease_grading_id = glaucoma_consensus_label.id
LEFT JOIN users glaucoma_consensus_decider_u ON glaucoma_consensus.decided_by_user_id = glaucoma_consensus_decider_u.id

LEFT JOIN consensus amd_consensus ON gt.id = amd_consensus.task_id AND d.name = 'AMD'
LEFT JOIN disease_gradings amd_consensus_label ON amd_consensus.final_disease_grading_id = amd_consensus_label.id
LEFT JOIN users amd_consensus_decider_u ON amd_consensus.decided_by_user_id = amd_consensus_decider_u.id

LEFT JOIN consensus additional_consensus ON gt.id = additional_consensus.task_id
LEFT JOIN users additional_consensus_decider_u ON additional_consensus.decided_by_user_id = additional_consensus_decider_u.id

-- ==========================================
-- DISEASE REPORT JOINS
-- ==========================================
LEFT JOIN diabetic_retinopathy_reports dr ON pe.id = dr.patient_encounter_id
LEFT JOIN glaucoma_results_cleaned grc ON pe.id = grc.patient_encounter_id

-- ==========================================
-- GROUPING FOR AGGREGATION
-- ==========================================
GROUP BY
  pe.id, h.id, lu.id,
  dr.id, grc.id,
  dr_consensus.id, glaucoma_consensus.id, amd_consensus.id;
```

### Refresh Function

```sql
CREATE OR REPLACE FUNCTION refresh_encounter_pivot() RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_encounter_pivot;
END;
$$ LANGUAGE plpgsql;
```

## Performance & Optimization

### Comprehensive Indexing Strategy (35+ Indexes)

```sql
-- ==========================================
-- CORE IDENTIFICATION INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_encounter_id ON mvw_encounter_pivot(encounter_id);
CREATE INDEX idx_mvw_encounter_pivot_patient_id ON mvw_encounter_pivot(patient_identifier);
CREATE INDEX idx_mvw_encounter_pivot_encounter_name ON mvw_encounter_pivot(encounter_name);

-- ==========================================
-- VERIFICATION STATUS INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_encounter_verified ON mvw_encounter_pivot(encounter_verified_status);
CREATE INDEX idx_mvw_encounter_pivot_glaucoma_verified ON mvw_encounter_pivot(glaucoma_verified_status);
CREATE INDEX idx_mvw_encounter_pivot_dr_verified ON mvw_encounter_pivot(dr_verified_status);

-- ==========================================
-- CONTEXT INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_hospital_id ON mvw_encounter_pivot(hospital_id);
CREATE INDEX idx_mvw_encounter_pivot_hospital_name ON mvw_encounter_pivot(hospital_name);
CREATE INDEX idx_mvw_encounter_pivot_lab_unit_id ON mvw_encounter_pivot(lab_unit_id);
CREATE INDEX idx_mvw_encounter_pivot_lab_unit_name ON mvw_encounter_pivot(lab_unit_name);

-- ==========================================
-- DISEASE RESULTS INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_dr_result ON mvw_encounter_pivot(dr_result);
CREATE INDEX idx_mvw_encounter_pivot_dr_qualitative ON mvw_encounter_pivot(dr_qualitative_result);
CREATE INDEX idx_mvw_encounter_pivot_glaucoma_result ON mvw_encounter_pivot(glaucoma_result);
CREATE INDEX idx_mvw_encounter_pivot_glaucoma_qualitative ON mvw_encounter_pivot(glaucoma_qualitative_result);
CREATE INDEX idx_mvw_encounter_pivot_vcdr_right ON mvw_encounter_pivot(glaucoma_vcdr_right_num);
CREATE INDEX idx_mvw_encounter_pivot_vcdr_left ON mvw_encounter_pivot(glaucoma_vcdr_left_num);

-- ==========================================
-- IMAGE ANALYSIS INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_total_images ON mvw_encounter_pivot(total_images);
CREATE INDEX idx_mvw_encounter_pivot_image_uuids ON mvw_encounter_pivot USING GIN(image_uuids);
CREATE INDEX idx_mvw_encounter_pivot_eye_sides ON mvw_encounter_pivot USING GIN(eye_sides);

-- ==========================================
-- TASK ANALYSIS INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_dr_tasks ON mvw_encounter_pivot(dr_task_count);
CREATE INDEX idx_mvw_encounter_pivot_glaucoma_tasks ON mvw_encounter_pivot(glaucoma_task_count);
CREATE INDEX idx_mvw_encounter_pivot_amd_tasks ON mvw_encounter_pivot(amd_task_count);
CREATE INDEX idx_mvw_encounter_pivot_additional_tasks ON mvw_encounter_pivot(additional_disease_task_count);
CREATE INDEX idx_mvw_encounter_pivot_total_tasks ON mvw_encounter_pivot(total_task_count);

-- ==========================================
-- TASK STATUS INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_pending_tasks ON mvw_encounter_pivot(pending_tasks);
CREATE INDEX idx_mvw_encounter_pivot_resident_done_tasks ON mvw_encounter_pivot(resident_done_tasks);
CREATE INDEX idx_mvw_encounter_pivot_resident2_done_tasks ON mvw_encounter_pivot(resident2_done_tasks);
CREATE INDEX idx_mvw_encounter_pivot_arbitration_tasks ON mvw_encounter_pivot(arbitration_tasks);
CREATE INDEX idx_mvw_encounter_pivot_final_tasks ON mvw_encounter_pivot(final_tasks);

-- ==========================================
-- TIME-BASED INDEXES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_created_at ON mvw_encounter_pivot(encounter_created_at);
CREATE INDEX idx_mvw_encounter_pivot_updated_at ON mvw_encounter_pivot(encounter_updated_at);
CREATE INDEX idx_mvw_encounter_pivot_last_grading ON mvw_encounter_pivot(last_grading_activity);
CREATE INDEX idx_mvw_encounter_pivot_freshness ON mvw_encounter_pivot(data_freshness_minutes);

-- ==========================================
-- JSON QUERY INDEXES (Critical for Performance)
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_image_grades ON mvw_encounter_pivot USING GIN(image_grade_pivots);
CREATE INDEX idx_mvw_encounter_pivot_image_grades_jsonb ON mvw_encounter_pivot USING GIN((image_grade_pivots::jsonb));

-- ==========================================
-- COMPOSITE INDEXES FOR COMMON QUERIES
-- ==========================================
CREATE INDEX idx_mvw_encounter_pivot_hospital_glaucoma ON mvw_encounter_pivot(hospital_id, glaucoma_result);
CREATE INDEX idx_mvw_encounter_pivot_lab_dr_status ON mvw_encounter_pivot(lab_unit_id, dr_result, dr_verified_status);
CREATE INDEX idx_mvw_encounter_pivot_tasks_pending ON mvw_encounter_pivot(total_tasks, pending_tasks);
CREATE INDEX idx_mvw_encounter_pivot_time_freshness ON mvw_encounter_pivot(encounter_created_at, data_freshness_minutes);
```

## Integration Plan

### Migration File Structure

```python
# File: migrations/versions/<timestamp>_create_encounter_pivot_view.py
"""Create encounter pivot materialized view

Revision ID: xyz_create_encounter_pivot_view
Revises: 01096ff074fa
Create Date: 2025-11-11 <timestamp>

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = 'xyz_create_encounter_pivot_view'
down_revision: Union[str, Sequence[str], None] = '01096ff074fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create the materialized view
    op.execute("""
    CREATE MATERIALIZED VIEW mvw_encounter_pivot AS
    -- [Insert complete SQL from Technical Specifications section]
    """)

    # Create refresh function
    op.execute("""
    CREATE OR REPLACE FUNCTION refresh_encounter_pivot() RETURNS void AS $$
    BEGIN
      REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_encounter_pivot;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # Create all indexes (35+ indexes from Performance section)
    # [Insert all CREATE INDEX statements]

def downgrade() -> None:
    # Drop indexes in reverse order
    # [Insert all DROP INDEX statements]

    # Drop refresh function
    op.execute("DROP FUNCTION IF EXISTS refresh_encounter_pivot()")

    # Drop materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_encounter_pivot")
```

### APS Scheduler Integration

```python
# Add to utils/materialized_view_scheduler.py
SCHEDULED_VIEWS['encounter_pivot'] = {
    'refresh_function': 'refresh_encounter_pivot()',
    'description': 'Comprehensive encounter-centric analytics view',
    'priority': 'high',
    'dependencies': []  # No dependencies - uses base tables
}
```

### Admin Interface Integration

```python
# Add to admin/materialized_view_status.py
VIEW_STATUS['encounter_pivot'] = {
    'name': 'Encounter Pivot View',
    'description': 'Comprehensive encounter-level analytics with individual image grade pivots',
    'refresh_function': 'refresh_encounter_pivot',
    'monitoring': True,
    'size_estimation': 'large'  # Due to JSON structure
}
```

## Usage Examples & Query Patterns

### Research Query Examples

```sql
-- ==========================================
-- CLINICAL RESEARCH PATTERNS
-- ==========================================

-- Find encounters with specific DR and Glaucoma grade combinations
SELECT
  encounter_id,
  patient_identifier,
  capture_date,
  image_grade_pivots
FROM mvw_encounter_pivot
WHERE dr_result = 'Moderate NPDR'
  AND glaucoma_vcdr_right_num > 0.7
  AND total_images > 0;

-- Analyze grader consistency across all diseases
SELECT
  hospital_name,
  COUNT(*) as total_encounters,
  COUNT(CASE WHEN dr_consensus_method = 'adjudication' THEN 1 END) as dr_adjudications,
  COUNT(CASE WHEN glaucoma_consensus_method = 'adjudication' THEN 1 END) as glaucoma_adjudications,
  COUNT(CASE WHEN amd_consensus_method = 'adjudication' THEN 1 END) as amd_adjudications
FROM mvw_encounter_pivot
WHERE total_task_count > 0
GROUP BY hospital_name;

-- Find images with AI vs human disagreement
SELECT
  encounter_id,
  image_grade_pivots
FROM mvw_encounter_pivot
WHERE image_grade_pivots @> '[{
  "dr_ai_grade": "Severe NPDR",
  "dr_consensus_grade": "Mild NPDR"
}]' OR image_grade_pivots @> '[{
  "glaucoma_ai_grade": "Glaucoma",
  "glaucoma_consensus_grade": "Normal"
}]';

-- ==========================================
-- QUALITY ASSURANCE PATTERNS
-- ==========================================

-- Check verification completeness
SELECT
  COUNT(*) as total_encounters,
  COUNT(CASE WHEN dr_verified_status = 'verified' THEN 1 END) as dr_verified,
  COUNT(CASE WHEN glaucoma_verified_status = 'verified' THEN 1 END) as glaucoma_verified,
  COUNT(CASE WHEN encounter_verified_status = 'verified' THEN 1 END) as encounter_verified
FROM mvw_encounter_pivot;

-- Identify encounters with incomplete grading
SELECT
  encounter_id,
  total_images,
  dr_task_count,
  glaucoma_task_count,
  pending_tasks
FROM mvw_encounter_pivot
WHERE pending_tasks > 0
  OR (total_images > 0 AND dr_task_count = 0)
  OR (total_images > 0 AND glaucoma_task_count = 0);

-- Data freshness analysis
SELECT
  hospital_name,
  AVG(data_freshness_minutes) as avg_data_freshness,
  AVG(grading_freshness_minutes) as avg_grading_freshness,
  COUNT(*) as encounter_count
FROM mvw_encounter_pivot
GROUP BY hospital_name
ORDER BY avg_data_freshness DESC;

-- ==========================================
-- OPERATIONAL REPORTING PATTERNS
-- ==========================================

-- Grading workload by hospital and disease
SELECT
  hospital_name,
  SUM(dr_task_count) as dr_workload,
  SUM(glaucoma_task_count) as glaucoma_workload,
  SUM(amd_task_count) as amd_workload,
  SUM(pending_tasks) as pending_workload,
  COUNT(*) as total_encounters
FROM mvw_encounter_pivot
GROUP BY hospital_name
ORDER BY dr_workload DESC;

-- Consensus method analysis
SELECT
  dr_consensus_method,
  COUNT(*) as encounter_count,
  COUNT(CASE WHEN glaucoma_consensus_method = dr_consensus_method THEN 1 END) as matching_glaucoma_method
FROM mvw_encounter_pivot
WHERE dr_consensus_method IS NOT NULL
GROUP BY dr_consensus_method;

-- Time-based trend analysis
SELECT
  DATE_TRUNC('month', encounter_created_at) as month,
  COUNT(*) as encounters_created,
  SUM(total_images) as total_images,
  AVG(total_task_count) as avg_tasks_per_encounter
FROM mvw_encounter_pivot
WHERE encounter_created_at >= NOW() - INTERVAL '12 months'
GROUP BY DATE_TRUNC('month', encounter_created_at)
ORDER BY month DESC;
```

### JSON Query Examples

```sql
-- ==========================================
-- ADVANCED JSON QUERY PATTERNS
-- ==========================================

-- Find images with specific feature selections
SELECT
  encounter_id,
  image_grade_pivots
FROM mvw_encounter_pivot
WHERE image_grade_pivots @> '[{
  "dr_resident_features": "[{\\"label\\": \\"Microaneurysms\\"}]"
}]';

-- Analyze AI model performance
SELECT
  json_array_elements(image_grade_pivots)->>'dr_ai_model_name' as ai_model,
  COUNT(*) as usage_count,
  AVG((json_array_elements(image_grade_pivots)->>'dr_ai_confidence')::float) as avg_confidence
FROM mvw_encounter_pivot
WHERE json_array_elements(image_grade_pivots)->>'dr_ai_model_name' IS NOT NULL
GROUP BY json_array_elements(image_grade_pivots)->>'dr_ai_model_name';

-- Cross-disease grade correlation analysis
SELECT
  encounter_id,
  json_array_elements(image_grade_pivots)->>'dr_resident_grade' as dr_grade,
  json_array_elements(image_grade_pivots)->>'glaucoma_resident_grade' as glaucoma_grade
FROM mvw_encounter_pivot
WHERE json_array_elements(image_grade_pivots)->>'dr_resident_grade' IS NOT NULL
  AND json_array_elements(image_grade_pivots)->>'glaucoma_resident_grade' IS NOT NULL;
```

## Implementation Timeline

### Phase 1: Development & Testing (Week 1-2)
- [ ] Create migration file with complete SQL DDL
- [ ] Implement all 35+ performance indexes
- [ ] Create refresh function
- [ ] Test view creation and basic functionality

### Phase 2: Integration (Week 2-3)
- [ ] Integrate with APS scheduler
- [ ] Add to admin materialized view interface
- [ ] Update comprehensive documentation
- [ ] Create monitoring and alerting

### Phase 3: Validation & Performance (Week 3-4)
- [ ] Performance testing with production data
- [ ] Query optimization and index tuning
- [ ] Data accuracy validation
- [ ] User acceptance testing

### Phase 4: Deployment (Week 4)
- [ ] Production deployment
- [ ] Initial data population
- [ ] Monitoring setup
- [ ] User training and documentation

### Testing & Validation Procedures

1. **Data Accuracy Testing**
   - Compare view results with direct database queries
   - Validate JSON structure integrity
   - Check NULL value handling

2. **Performance Testing**
   - Query response time analysis
   - Index usage verification
   - Concurrent access testing

3. **Integration Testing**
   - APS scheduler functionality
   - Admin interface integration
   - Refresh mechanism validation

### Deployment Checklist

- [ ] Migration file reviewed and tested
- [ ] All indexes created successfully
- [ ] Refresh function operational
- [ ] APS scheduler integration complete
- [ ] Admin interface updated
- [ ] Documentation updated
- [ ] Monitoring configured
- [ ] Rollback plan prepared
- [ ] User communication complete

## Expected Benefits & Impact

### Research Benefits
1. **Comprehensive Data Access**: Single query for complete encounter analysis
2. **Individual Image Tracking**: Detailed grade-by-grade analysis capabilities
3. **Cross-Disease Analysis**: Easy correlation between DR, Glaucoma, and AMD results
4. **Historical Preservation**: Complete audit trail with timestamps and feature selections

### Operational Benefits
1. **Performance Optimization**: 35+ indexes for fast analytics queries
2. **Simplified Reporting**: Eliminates complex JOIN operations
3. **Real-time Insights**: Freshness metrics and activity tracking
4. **Quality Assurance**: Verification status monitoring and completion tracking

### Future Extensibility
1. **New Disease Support**: Easy addition of new diseases through additional_diseases JSON
2. **AI Model Integration**: Dynamic AI model tracking with confidence scores
3. **Advanced Analytics**: JSON structure enables complex feature analysis
4. **Machine Learning Ready**: Structured data suitable for ML model training

This comprehensive encounter pivot materialized view will serve as a foundational analytics resource for the Fundus Image Manager, enabling advanced research capabilities while maintaining optimal performance for operational use cases.