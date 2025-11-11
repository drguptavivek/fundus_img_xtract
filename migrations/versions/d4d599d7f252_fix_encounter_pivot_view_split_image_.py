"""Fix encounter pivot view - split image_grade_pivots by disease and fix task counts

Revision ID: d4d599d7f252
Revises: 1ea459b0d658
Create Date: 2025-11-11 17:21:36.039724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4d599d7f252'
down_revision: Union[str, Sequence[str], None] = '1ea459b0d658'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop existing materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_encounter_pivot")

    # Create the improved encounter pivot materialized view with split image_grade_pivots
    op.execute("""
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
      -- IMAGE AGGREGATION
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
      -- SPLIT IMAGE-GRADE PIVOTS BY DISEASE
      -- ==========================================
      -- DR Image Grades (Only DR-related grades)
      COALESCE(json_agg(
        CASE WHEN ef.id IS NOT NULL THEN
          jsonb_build_object(
            'image_id', ef.id,
            'image_uuid', ef.uuid,
            'eye_side', ef.eye_side,
            'file_type', ef.file_type,
            'resident_grade', COALESCE(dr_resident.impression, ''),
            'resident2_grade', COALESCE(dr_resident2.impression, ''),
            'arbitrator_grade', COALESCE(dr_arbitrator.impression, ''),
            'ai_grade', COALESCE(dr_ai.impression, ''),
            'review_grade', COALESCE(dr_review.impression, ''),
            'consensus_grade', COALESCE(dr_consensus_label.impression, '')
          )
        END
      ) FILTER (WHERE ef.id IS NOT NULL), '[]'::json) as dr_image_grades,

      -- Glaucoma Image Grades (Only Glaucoma-related grades)
      COALESCE(json_agg(
        CASE WHEN ef.id IS NOT NULL THEN
          jsonb_build_object(
            'image_id', ef.id,
            'image_uuid', ef.uuid,
            'eye_side', ef.eye_side,
            'file_type', ef.file_type,
            'resident_grade', COALESCE(glaucoma_resident.impression, ''),
            'resident2_grade', COALESCE(glaucoma_resident2.impression, ''),
            'arbitrator_grade', COALESCE(glaucoma_arbitrator.impression, ''),
            'ai_grade', COALESCE(glaucoma_ai.impression, ''),
            'review_grade', COALESCE(glaucoma_review.impression, ''),
            'consensus_grade', COALESCE(glaucoma_consensus_label.impression, '')
          )
        END
      ) FILTER (WHERE ef.id IS NOT NULL), '[]'::json) as glaucoma_image_grades,

      -- AMD Image Grades (Only AMD-related grades)
      COALESCE(json_agg(
        CASE WHEN ef.id IS NOT NULL THEN
          jsonb_build_object(
            'image_id', ef.id,
            'image_uuid', ef.uuid,
            'eye_side', ef.eye_side,
            'file_type', ef.file_type,
            'resident_grade', COALESCE(amd_resident.impression, ''),
            'resident2_grade', COALESCE(amd_resident2.impression, ''),
            'arbitrator_grade', COALESCE(amd_arbitrator.impression, ''),
            'ai_grade', COALESCE(amd_ai.impression, ''),
            'review_grade', COALESCE(amd_review.impression, ''),
            'consensus_grade', COALESCE(amd_consensus_label.impression, '')
          )
        END
      ) FILTER (WHERE ef.id IS NOT NULL), '[]'::json) as amd_image_grades,

      -- Additional Disease Image Grades (All other diseases)
      COALESCE(json_agg(
        CASE WHEN ef.id IS NOT NULL THEN
          jsonb_build_object(
            'image_id', ef.id,
            'image_uuid', ef.uuid,
            'eye_side', ef.eye_side,
            'file_type', ef.file_type,
            'disease_name', COALESCE(additional_d.name, ''),
            'resident_grade', COALESCE(additional_resident.impression, ''),
            'resident2_grade', COALESCE(additional_resident2.impression, ''),
            'arbitrator_grade', COALESCE(additional_arbitrator.impression, ''),
            'ai_grade', COALESCE(additional_ai.impression, ''),
            'review_grade', COALESCE(additional_review.impression, ''),
            'consensus_grade', COALESCE(additional_consensus_label.impression, '')
          )
        END
      ) FILTER (WHERE ef.id IS NOT NULL AND additional_d.name IS NOT NULL), '[]'::json) as additional_disease_image_grades,

      -- ==========================================
      -- TASK SUMMARY BY DISEASE
      -- ==========================================
      COUNT(DISTINCT CASE WHEN d.name = 'Diabetic Retinopathy' THEN gt.id END) as dr_task_count,
      COUNT(DISTINCT CASE WHEN d.name = 'Glaucoma' THEN gt.id END) as glaucoma_task_count,
      COUNT(DISTINCT CASE WHEN d.name = 'AMD' THEN gt.id END) as amd_task_count,
      COUNT(DISTINCT CASE WHEN d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD') THEN gt.id END) as additional_disease_task_count,
      COUNT(DISTINCT gt.id) as total_task_count,

      -- Task status breakdown
      COUNT(DISTINCT CASE WHEN gt.state = 'completed' THEN gt.id END) as completed_task_count,
      COUNT(DISTINCT CASE WHEN gt.state = 'pending' THEN gt.id END) as pending_task_count,
      COUNT(DISTINCT CASE WHEN gt.state = 'in_progress' THEN gt.id END) as in_progress_task_count,
      MAX(gt.updated_at) as last_task_activity_at,

      -- ==========================================
      -- CONSENSUS SUMMARY
      -- ==========================================
      COUNT(DISTINCT CASE WHEN c.id IS NOT NULL THEN c.id END) as consensus_count,
      MAX(c.decided_at) as last_consensus_at

    FROM patient_encounters pe
    -- ==========================================
    -- CORE TABLE JOINS
    -- ==========================================
    LEFT JOIN lab_units lu ON pe.lab_unit_id = lu.id
    LEFT JOIN hospitals h ON lu.hospital_id = h.id

    -- Encounter Files (Images from ZIP uploads)
    LEFT JOIN encounter_files ef ON pe.id = ef.patient_encounter_id

    -- Grading Tasks (All sources)
    LEFT JOIN grading_tasks gt ON ef.id = gt.encounter_file_id

    -- Disease Information
    LEFT JOIN diseases d ON gt.disease_id = d.id

    -- ==========================================
    -- DISEASE REPORT JOINS
    -- ==========================================
    LEFT JOIN diabetic_retinopathy_reports dr ON pe.id = dr.patient_encounter_id
    LEFT JOIN glaucoma_results_cleaned grc ON pe.id = grc.patient_encounter_id

    -- ==========================================
    -- DR GRADE JOINS
    -- ==========================================
    LEFT JOIN grades dr_resident_g ON gt.id = dr_resident_g.task_id AND dr_resident_g.role_slot = 'resident' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_resident ON dr_resident_g.disease_grading_id = dr_resident.id

    LEFT JOIN grades dr_resident2_g ON gt.id = dr_resident2_g.task_id AND dr_resident2_g.role_slot = 'resident2' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_resident2 ON dr_resident2_g.disease_grading_id = dr_resident2.id

    LEFT JOIN grades dr_arbitrator_g ON gt.id = dr_arbitrator_g.task_id AND dr_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_arbitrator ON dr_arbitrator_g.disease_grading_id = dr_arbitrator.id

    LEFT JOIN grades dr_ai_g ON gt.id = dr_ai_g.task_id AND dr_ai_g.role_slot = 'ai' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_ai ON dr_ai_g.disease_grading_id = dr_ai.id

    LEFT JOIN grades dr_review_g ON gt.id = dr_review_g.task_id AND dr_review_g.role_slot = 'review' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_review ON dr_review_g.disease_grading_id = dr_review.id

    -- ==========================================
    -- GLAUCOMA GRADE JOINS
    -- ==========================================
    LEFT JOIN grades glaucoma_resident_g ON gt.id = glaucoma_resident_g.task_id AND glaucoma_resident_g.role_slot = 'resident' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_resident ON glaucoma_resident_g.disease_grading_id = glaucoma_resident.id

    LEFT JOIN grades glaucoma_resident2_g ON gt.id = glaucoma_resident2_g.task_id AND glaucoma_resident2_g.role_slot = 'resident2' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_resident2 ON glaucoma_resident2_g.disease_grading_id = glaucoma_resident2.id

    LEFT JOIN grades glaucoma_arbitrator_g ON gt.id = glaucoma_arbitrator_g.task_id AND glaucoma_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_arbitrator ON glaucoma_arbitrator_g.disease_grading_id = glaucoma_arbitrator.id

    LEFT JOIN grades glaucoma_ai_g ON gt.id = glaucoma_ai_g.task_id AND glaucoma_ai_g.role_slot = 'ai' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_ai ON glaucoma_ai_g.disease_grading_id = glaucoma_ai.id

    LEFT JOIN grades glaucoma_review_g ON gt.id = glaucoma_review_g.task_id AND glaucoma_review_g.role_slot = 'review' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_review ON glaucoma_review_g.disease_grading_id = glaucoma_review.id

    -- ==========================================
    -- AMD GRADE JOINS
    -- ==========================================
    LEFT JOIN grades amd_resident_g ON gt.id = amd_resident_g.task_id AND amd_resident_g.role_slot = 'resident' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_resident ON amd_resident_g.disease_grading_id = amd_resident.id

    LEFT JOIN grades amd_resident2_g ON gt.id = amd_resident2_g.task_id AND amd_resident2_g.role_slot = 'resident2' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_resident2 ON amd_resident2_g.disease_grading_id = amd_resident2.id

    LEFT JOIN grades amd_arbitrator_g ON gt.id = amd_arbitrator_g.task_id AND amd_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_arbitrator ON amd_arbitrator_g.disease_grading_id = amd_arbitrator.id

    LEFT JOIN grades amd_ai_g ON gt.id = amd_ai_g.task_id AND amd_ai_g.role_slot = 'ai' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_ai ON amd_ai_g.disease_grading_id = amd_ai.id

    LEFT JOIN grades amd_review_g ON gt.id = amd_review_g.task_id AND amd_review_g.role_slot = 'review' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_review ON amd_review_g.disease_grading_id = amd_review.id

    -- ==========================================
    -- ADDITIONAL DISEASE GRADE JOINS
    -- ==========================================
    LEFT JOIN grades additional_resident_g ON gt.id = additional_resident_g.task_id AND additional_resident_g.role_slot = 'resident' AND d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD')
    LEFT JOIN disease_gradings additional_resident ON additional_resident_g.disease_grading_id = additional_resident.id

    LEFT JOIN grades additional_resident2_g ON gt.id = additional_resident2_g.task_id AND additional_resident2_g.role_slot = 'resident2' AND d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD')
    LEFT JOIN disease_gradings additional_resident2 ON additional_resident2_g.disease_grading_id = additional_resident2.id

    LEFT JOIN grades additional_arbitrator_g ON gt.id = additional_arbitrator_g.task_id AND additional_arbitrator_g.role_slot = 'arbitrator' AND d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD')
    LEFT JOIN disease_gradings additional_arbitrator ON additional_arbitrator_g.disease_grading_id = additional_arbitrator.id

    LEFT JOIN grades additional_ai_g ON gt.id = additional_ai_g.task_id AND additional_ai_g.role_slot = 'ai' AND d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD')
    LEFT JOIN disease_gradings additional_ai ON additional_ai_g.disease_grading_id = additional_ai.id

    LEFT JOIN grades additional_review_g ON gt.id = additional_review_g.task_id AND additional_review_g.role_slot = 'review' AND d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD')
    LEFT JOIN disease_gradings additional_review ON additional_review_g.disease_grading_id = additional_review.id

    LEFT JOIN diseases additional_d ON additional_d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD') AND additional_d.id = gt.disease_id

    -- ==========================================
    -- CONSENSUS JOINS
    -- ==========================================
    LEFT JOIN consensus c ON gt.id = c.task_id

    -- Consensus joins for each disease
    LEFT JOIN consensus dr_consensus ON gt.id = dr_consensus.task_id AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_consensus_label ON dr_consensus.final_disease_grading_id = dr_consensus_label.id

    LEFT JOIN consensus glaucoma_consensus ON gt.id = glaucoma_consensus.task_id AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_consensus_label ON glaucoma_consensus.final_disease_grading_id = glaucoma_consensus_label.id

    LEFT JOIN consensus amd_consensus ON gt.id = amd_consensus.task_id AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_consensus_label ON amd_consensus.final_disease_grading_id = amd_consensus_label.id

    LEFT JOIN consensus additional_consensus ON gt.id = additional_consensus.task_id AND d.name NOT IN ('Diabetic Retinopathy', 'Glaucoma', 'AMD')
    LEFT JOIN disease_gradings additional_consensus_label ON additional_consensus.final_disease_grading_id = additional_consensus_label.id

    GROUP BY pe.id, h.id, lu.id, dr.id, grc.id
    ORDER BY pe.id DESC;
    """)

    # Create comprehensive indexes for the improved materialized view
    # Primary Key and Core Indexes
    op.execute("CREATE UNIQUE INDEX idx_mvw_encounter_pivot_pkey ON mvw_encounter_pivot(encounter_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_hospital ON mvw_encounter_pivot(hospital_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_lab_unit ON mvw_encounter_pivot(lab_unit_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_capture_date ON mvw_encounter_pivot(capture_date)")

    # Disease Result Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_result ON mvw_encounter_pivot(dr_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_result ON mvw_encounter_pivot(glaucoma_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_qualitative ON mvw_encounter_pivot(dr_qualitative_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_qualitative ON mvw_encounter_pivot(glaucoma_qualitative_result)")

    # Task Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_tasks ON mvw_encounter_pivot(dr_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_tasks ON mvw_encounter_pivot(glaucoma_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_amd_tasks ON mvw_encounter_pivot(amd_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_additional_tasks ON mvw_encounter_pivot(additional_disease_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_tasks ON mvw_encounter_pivot(total_task_count)")

    # Task Status Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_completed_tasks ON mvw_encounter_pivot(completed_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_pending_tasks ON mvw_encounter_pivot(pending_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_in_progress_tasks ON mvw_encounter_pivot(in_progress_task_count)")

    # Image Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_images ON mvw_encounter_pivot(total_images)")

    # JSON Query Indexes for Split Image Grades
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_image_grades ON mvw_encounter_pivot USING GIN((dr_image_grades::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_image_grades ON mvw_encounter_pivot USING GIN((glaucoma_image_grades::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_amd_image_grades ON mvw_encounter_pivot USING GIN((amd_image_grades::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_additional_image_grades ON mvw_encounter_pivot USING GIN((additional_disease_image_grades::jsonb))")

    # General JSON Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_image_uuids ON mvw_encounter_pivot USING GIN((image_uuids::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_eye_sides ON mvw_encounter_pivot USING GIN((eye_sides::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_image_types ON mvw_encounter_pivot USING GIN((image_types::jsonb))")

    # Composite Indexes for Common Queries
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_hospital_glaucoma ON mvw_encounter_pivot(hospital_id, glaucoma_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_lab_dr_status ON mvw_encounter_pivot(lab_unit_id, dr_result, dr_verified_status)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_capture_date_hospital ON mvw_encounter_pivot(capture_date, hospital_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_images_tasks ON mvw_encounter_pivot(total_images, total_task_count)")

    # Time-based Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_last_activity ON mvw_encounter_pivot(last_task_activity_at)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_updated ON mvw_encounter_pivot(glaucoma_result_updated_at)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_last_consensus ON mvw_encounter_pivot(last_consensus_at)")

    # Consensus Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_consensus_count ON mvw_encounter_pivot(consensus_count)")

    print("Created improved mvw_encounter_pivot with split image_grade_pivots and comprehensive indexing")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the improved materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_encounter_pivot")

    # Recreate the original materialized view with single image_grade_pivots column
    op.execute("""
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
      -- INDIVIDUAL IMAGE-GRADE PIVOTS (Original Single Column)
      -- ==========================================
      -- Each image has basic grading information for all diseases combined
      COALESCE(json_agg(
        CASE WHEN ef.id IS NOT NULL THEN
          jsonb_build_object(
            'image_id', ef.id,
            'image_uuid', ef.uuid,
            'eye_side', ef.eye_side,
            'file_type', ef.file_type,
            'dr_resident_grade', COALESCE(dr_resident.impression, ''),
            'dr_resident2_grade', COALESCE(dr_resident2.impression, ''),
            'dr_arbitrator_grade', COALESCE(dr_arbitrator.impression, ''),
            'dr_ai_grade', COALESCE(dr_ai.impression, ''),
            'dr_consensus_grade', COALESCE(dr_consensus_label.impression, ''),
            'glaucoma_resident_grade', COALESCE(glaucoma_resident.impression, ''),
            'glaucoma_resident2_grade', COALESCE(glaucoma_resident2.impression, ''),
            'glaucoma_arbitrator_grade', COALESCE(glaucoma_arbitrator.impression, ''),
            'glaucoma_ai_grade', COALESCE(glaucoma_ai.impression, ''),
            'glaucoma_consensus_grade', COALESCE(glaucoma_consensus_label.impression, ''),
            'amd_resident_grade', COALESCE(amd_resident.impression, ''),
            'amd_resident2_grade', COALESCE(amd_resident2.impression, ''),
            'amd_arbitrator_grade', COALESCE(amd_arbitrator.impression, ''),
            'amd_ai_grade', COALESCE(amd_ai.impression, ''),
            'amd_consensus_grade', COALESCE(amd_consensus_label.impression, '')
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
      COUNT(DISTINCT CASE WHEN gt.state = 'completed' THEN gt.id END) as completed_task_count,
      COUNT(DISTINCT CASE WHEN gt.state = 'pending' THEN gt.id END) as pending_task_count,
      COUNT(DISTINCT CASE WHEN gt.state = 'in_progress' THEN gt.id END) as in_progress_task_count,
      MAX(gt.updated_at) as last_task_activity_at,

      -- ==========================================
      -- CONSENSUS SUMMARY
      -- ==========================================
      COUNT(DISTINCT CASE WHEN c.id IS NOT NULL THEN c.id END) as consensus_count,
      MAX(c.decided_at) as last_consensus_at

    FROM patient_encounters pe
    -- ==========================================
    -- CORE TABLE JOINS
    -- ==========================================
    LEFT JOIN lab_units lu ON pe.lab_unit_id = lu.id
    LEFT JOIN hospitals h ON lu.hospital_id = h.id

    -- Encounter Files (Images from ZIP uploads)
    LEFT JOIN encounter_files ef ON pe.id = ef.patient_encounter_id

    -- Grading Tasks (All sources)
    LEFT JOIN grading_tasks gt ON ef.id = gt.encounter_file_id

    -- Disease Information
    LEFT JOIN diseases d ON gt.disease_id = d.id

    -- ==========================================
    -- DISEASE REPORT JOINS
    -- ==========================================
    LEFT JOIN diabetic_retinopathy_reports dr ON pe.id = dr.patient_encounter_id
    LEFT JOIN glaucoma_results_cleaned grc ON pe.id = grc.patient_encounter_id

    -- ==========================================
    -- DR GRADE JOINS
    -- ==========================================
    LEFT JOIN grades dr_resident_g ON gt.id = dr_resident_g.task_id AND dr_resident_g.role_slot = 'resident' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_resident ON dr_resident_g.disease_grading_id = dr_resident.id

    LEFT JOIN grades dr_resident2_g ON gt.id = dr_resident2_g.task_id AND dr_resident2_g.role_slot = 'resident2' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_resident2 ON dr_resident2_g.disease_grading_id = dr_resident2.id

    LEFT JOIN grades dr_arbitrator_g ON gt.id = dr_arbitrator_g.task_id AND dr_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_arbitrator ON dr_arbitrator_g.disease_grading_id = dr_arbitrator.id

    LEFT JOIN grades dr_ai_g ON gt.id = dr_ai_g.task_id AND dr_ai_g.role_slot = 'ai' AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_ai ON dr_ai_g.disease_grading_id = dr_ai.id

    LEFT JOIN consensus dr_consensus ON gt.id = dr_consensus.task_id AND d.name = 'Diabetic Retinopathy'
    LEFT JOIN disease_gradings dr_consensus_label ON dr_consensus.final_disease_grading_id = dr_consensus_label.id

    -- ==========================================
    -- GLAUCOMA GRADE JOINS
    -- ==========================================
    LEFT JOIN grades glaucoma_resident_g ON gt.id = glaucoma_resident_g.task_id AND glaucoma_resident_g.role_slot = 'resident' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_resident ON glaucoma_resident_g.disease_grading_id = glaucoma_resident.id

    LEFT JOIN grades glaucoma_resident2_g ON gt.id = glaucoma_resident2_g.task_id AND glaucoma_resident2_g.role_slot = 'resident2' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_resident2 ON glaucoma_resident2_g.disease_grading_id = glaucoma_resident2.id

    LEFT JOIN grades glaucoma_arbitrator_g ON gt.id = glaucoma_arbitrator_g.task_id AND glaucoma_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_arbitrator ON glaucoma_arbitrator_g.disease_grading_id = glaucoma_arbitrator.id

    LEFT JOIN grades glaucoma_ai_g ON gt.id = glaucoma_ai_g.task_id AND glaucoma_ai_g.role_slot = 'ai' AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_ai ON glaucoma_ai_g.disease_grading_id = glaucoma_ai.id

    LEFT JOIN consensus glaucoma_consensus ON gt.id = glaucoma_consensus.task_id AND d.name = 'Glaucoma'
    LEFT JOIN disease_gradings glaucoma_consensus_label ON glaucoma_consensus.final_disease_grading_id = glaucoma_consensus_label.id

    -- ==========================================
    -- AMD GRADE JOINS (From Ad-Hoc Tasks)
    -- ==========================================
    LEFT JOIN grades amd_resident_g ON gt.id = amd_resident_g.task_id AND amd_resident_g.role_slot = 'resident' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_resident ON amd_resident_g.disease_grading_id = amd_resident.id

    LEFT JOIN grades amd_resident2_g ON gt.id = amd_resident2_g.task_id AND amd_resident2_g.role_slot = 'resident2' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_resident2 ON amd_resident2_g.disease_grading_id = amd_resident2.id

    LEFT JOIN grades amd_arbitrator_g ON gt.id = amd_arbitrator_g.task_id AND amd_arbitrator_g.role_slot = 'arbitrator' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_arbitrator ON amd_arbitrator_g.disease_grading_id = amd_arbitrator.id

    LEFT JOIN grades amd_ai_g ON gt.id = amd_ai_g.task_id AND amd_ai_g.role_slot = 'ai' AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_ai ON amd_ai_g.disease_grading_id = amd_ai.id

    LEFT JOIN consensus amd_consensus ON gt.id = amd_consensus.task_id AND d.name = 'AMD'
    LEFT JOIN disease_gradings amd_consensus_label ON amd_consensus.final_disease_grading_id = amd_consensus_label.id

    -- ==========================================
    -- CONSENSUS JOINS
    -- ==========================================
    LEFT JOIN consensus c ON gt.id = c.task_id

    GROUP BY pe.id, h.id, lu.id, dr.id, grc.id
    ORDER BY pe.id DESC;
    """)

    # Recreate the original indexes
    # Primary Key and Core Indexes
    op.execute("CREATE UNIQUE INDEX idx_mvw_encounter_pivot_pkey ON mvw_encounter_pivot(encounter_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_hospital ON mvw_encounter_pivot(hospital_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_lab_unit ON mvw_encounter_pivot(lab_unit_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_capture_date ON mvw_encounter_pivot(capture_date)")

    # Disease Result Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_result ON mvw_encounter_pivot(dr_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_result ON mvw_encounter_pivot(glaucoma_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_qualitative ON mvw_encounter_pivot(dr_qualitative_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_qualitative ON mvw_encounter_pivot(glaucoma_qualitative_result)")

    # Task Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_tasks ON mvw_encounter_pivot(dr_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_tasks ON mvw_encounter_pivot(glaucoma_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_amd_tasks ON mvw_encounter_pivot(amd_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_additional_tasks ON mvw_encounter_pivot(additional_disease_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_tasks ON mvw_encounter_pivot(total_task_count)")

    # Task Status Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_completed_tasks ON mvw_encounter_pivot(completed_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_pending_tasks ON mvw_encounter_pivot(pending_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_in_progress_tasks ON mvw_encounter_pivot(in_progress_task_count)")

    # Image Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_images ON mvw_encounter_pivot(total_images)")

    # JSON Query Indexes (Critical for Performance) - Original single column
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_image_grades ON mvw_encounter_pivot USING GIN((image_grade_pivots::jsonb))")

    # General JSON Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_image_uuids ON mvw_encounter_pivot USING GIN((image_uuids::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_eye_sides ON mvw_encounter_pivot USING GIN((eye_sides::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_image_types ON mvw_encounter_pivot USING GIN((image_types::jsonb))")

    # Composite Indexes for Common Queries
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_hospital_glaucoma ON mvw_encounter_pivot(hospital_id, glaucoma_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_lab_dr_status ON mvw_encounter_pivot(lab_unit_id, dr_result, dr_verified_status)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_capture_date_hospital ON mvw_encounter_pivot(capture_date, hospital_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_images_tasks ON mvw_encounter_pivot(total_images, total_task_count)")

    # Time-based Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_last_activity ON mvw_encounter_pivot(last_task_activity_at)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_updated ON mvw_encounter_pivot(glaucoma_result_updated_at)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_last_consensus ON mvw_encounter_pivot(last_consensus_at)")

    # Consensus Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_consensus_count ON mvw_encounter_pivot(consensus_count)")

    print("Reverted to original mvw_encounter_pivot with single image_grade_pivots column")
