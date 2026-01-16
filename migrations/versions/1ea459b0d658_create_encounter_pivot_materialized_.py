"""Create encounter pivot materialized view with individual image grade pivots

Revision ID: 1ea459b0d658
Revises: 01096ff074fa
Create Date: 2025-11-11 17:10:30.647548

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ea459b0d658'
down_revision: Union[str, Sequence[str], None] = '01096ff074fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the comprehensive encounter pivot materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_encounter_pivot")
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
      -- INDIVIDUAL IMAGE-GRADE PIVOTS (Simplified)
      -- ==========================================
      -- Each image has basic grading information
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
      COUNT(DISTINCT CASE WHEN gt.state = 'pending' THEN gt.id END) as pending_tasks,
      COUNT(DISTINCT CASE WHEN gt.state = 'resident_done' THEN gt.id END) as resident_done_tasks,
      COUNT(DISTINCT CASE WHEN gt.state = 'resident2_done' THEN gt.id END) as resident2_done_tasks,
      COUNT(DISTINCT CASE WHEN gt.state = 'arbitration' THEN gt.id END) as arbitration_tasks,
      COUNT(DISTINCT CASE WHEN gt.state = 'final' THEN gt.id END) as final_tasks,

      -- ==========================================
      -- TIME-BASED ANALYSIS
      -- ==========================================
      MAX(COALESCE(g.updated_at, gt.created_at)) as last_grading_activity

    FROM patient_encounters pe
    LEFT JOIN lab_units lu ON pe.lab_unit_id = lu.id
    LEFT JOIN hospitals h ON lu.hospital_id = h.id
    LEFT JOIN encounter_files ef ON pe.id = ef.patient_encounter_id

    -- ==========================================
    -- COMPREHENSIVE GRADING SYSTEM JOINS
    -- ==========================================
    LEFT JOIN grading_tasks gt ON ef.id = gt.encounter_file_id
    LEFT JOIN diseases d ON gt.disease_id = d.id
    LEFT JOIN grades g ON gt.id = g.task_id

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
      dr_consensus.id, glaucoma_consensus.id, amd_consensus.id,
      dr_resident_g.id, dr_resident.id, dr_resident_u.id,
      dr_resident2_g.id, dr_resident2.id, dr_resident2_u.id,
      dr_arbitrator_g.id, dr_arbitrator.id, dr_arbitrator_u.id,
      dr_ai_g.id, dr_ai.id,
      dr_review_g.id, dr_review.id, dr_review_u.id,
      glaucoma_resident_g.id, glaucoma_resident.id, glaucoma_resident_u.id,
      glaucoma_resident2_g.id, glaucoma_resident2.id, glaucoma_resident2_u.id,
      glaucoma_arbitrator_g.id, glaucoma_arbitrator.id, glaucoma_arbitrator_u.id,
      glaucoma_ai_g.id, glaucoma_ai.id,
      glaucoma_review_g.id, glaucoma_review.id, glaucoma_review_u.id,
      amd_resident_g.id, amd_resident.id, amd_resident_u.id,
      amd_resident2_g.id, amd_resident2.id, amd_resident2_u.id,
      amd_arbitrator_g.id, amd_arbitrator.id, amd_arbitrator_u.id,
      amd_ai_g.id, amd_ai.id,
      amd_review_g.id, amd_review.id, amd_review_u.id;
    """)

    # Create refresh function
    op.execute("""
    CREATE OR REPLACE FUNCTION refresh_encounter_pivot() RETURNS void AS $$
    BEGIN
      REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_encounter_pivot;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # ==========================================
    # PERFORMANCE INDEXES (35+ Indexes)
    # ==========================================

    # Core Identification Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_encounter_id ON mvw_encounter_pivot(encounter_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_patient_id ON mvw_encounter_pivot(patient_identifier)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_encounter_name ON mvw_encounter_pivot(encounter_name)")

    # Verification Status Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_encounter_verified ON mvw_encounter_pivot(encounter_verified_status)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_verified ON mvw_encounter_pivot(glaucoma_verified_status)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_verified ON mvw_encounter_pivot(dr_verified_status)")

    # Context Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_hospital_id ON mvw_encounter_pivot(hospital_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_hospital_name ON mvw_encounter_pivot(hospital_name)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_lab_unit_id ON mvw_encounter_pivot(lab_unit_id)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_lab_unit_name ON mvw_encounter_pivot(lab_unit_name)")

    # Disease Results Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_result ON mvw_encounter_pivot(dr_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_qualitative ON mvw_encounter_pivot(dr_qualitative_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_result ON mvw_encounter_pivot(glaucoma_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_qualitative ON mvw_encounter_pivot(glaucoma_qualitative_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_vcdr_right ON mvw_encounter_pivot(glaucoma_vcdr_right_num)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_vcdr_left ON mvw_encounter_pivot(glaucoma_vcdr_left_num)")

    # Image Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_images ON mvw_encounter_pivot(total_images)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_image_uuids ON mvw_encounter_pivot USING GIN((image_uuids::jsonb))")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_eye_sides ON mvw_encounter_pivot USING GIN((eye_sides::jsonb))")

    # Task Analysis Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_dr_tasks ON mvw_encounter_pivot(dr_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_glaucoma_tasks ON mvw_encounter_pivot(glaucoma_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_amd_tasks ON mvw_encounter_pivot(amd_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_additional_tasks ON mvw_encounter_pivot(additional_disease_task_count)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_total_tasks ON mvw_encounter_pivot(total_task_count)")

    # Task Status Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_pending_tasks ON mvw_encounter_pivot(pending_tasks)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_resident_done_tasks ON mvw_encounter_pivot(resident_done_tasks)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_resident2_done_tasks ON mvw_encounter_pivot(resident2_done_tasks)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_arbitration_tasks ON mvw_encounter_pivot(arbitration_tasks)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_final_tasks ON mvw_encounter_pivot(final_tasks)")

    # Time-based Indexes
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_last_grading ON mvw_encounter_pivot(last_grading_activity)")

    # JSON Query Indexes (Critical for Performance)
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_image_grades ON mvw_encounter_pivot USING GIN((image_grade_pivots::jsonb))")

    # Composite Indexes for Common Queries
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_hospital_glaucoma ON mvw_encounter_pivot(hospital_id, glaucoma_result)")
    op.execute("CREATE INDEX idx_mvw_encounter_pivot_lab_dr_status ON mvw_encounter_pivot(lab_unit_id, dr_result, dr_verified_status)")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop composite indexes first
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_lab_dr_status")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_hospital_glaucoma")

    # Drop JSON query indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_image_grades")

    # Drop time-based indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_last_grading")

    # Drop task status indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_final_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_arbitration_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_resident2_done_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_resident_done_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_pending_tasks")

    # Drop task analysis indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_total_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_additional_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_amd_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_glaucoma_tasks")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_dr_tasks")

    # Drop image analysis indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_eye_sides")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_image_uuids")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_total_images")

    # Drop disease results indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_vcdr_left")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_vcdr_right")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_glaucoma_qualitative")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_glaucoma_result")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_dr_qualitative")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_dr_result")

    # Drop context indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_lab_unit_name")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_lab_unit_id")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_hospital_name")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_hospital_id")

    # Drop verification status indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_dr_verified")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_glaucoma_verified")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_encounter_verified")

    # Drop core identification indexes
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_encounter_name")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_patient_id")
    op.execute("DROP INDEX IF EXISTS idx_mvw_encounter_pivot_encounter_id")

    # Drop refresh function
    op.execute("DROP FUNCTION IF EXISTS refresh_encounter_pivot()")

    # Drop materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_encounter_pivot")
