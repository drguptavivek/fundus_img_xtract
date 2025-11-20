"""create_diabetic_retinopathy_grading_pivot_view

Revision ID: cee197bc69ef
Revises: b3ab758d04e3
Create Date: 2025-11-10 01:35:34.340411

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cee197bc69ef'
down_revision: Union[str, Sequence[str], None] = 'b3ab758d04e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create materialized view for Diabetic Retinopathy grading data with pivoted grader columns
    op.execute("""
        CREATE MATERIALIZED VIEW mvw_diabetic_retinopathy_grading_pivot AS
        SELECT
            -- Image Identification (unified from both sources)
            CASE
                WHEN ef.id IS NOT NULL THEN 'encounter_file'
                WHEN diu.id IS NOT NULL THEN 'direct_upload'
                ELSE 'unknown'
            END as image_source,
            COALESCE(ef.id, diu.id) as image_id,
            COALESCE(ef.uuid, diu.uuid) as image_uuid,
            COALESCE(ef.filename, diu.original_filename) as filename,
            ef.eye_side as eye_side,

            -- Context Information
            ef.patient_encounter_id,
            pe.name as patient_encounter_name,
            pe.patient_id as patient_identifier,
            pe.capture_date as capture_date,
            h.name as hospital_name,
            lu.name as lab_unit_name,
            cam.name as camera_name,

            -- DR-specific Information
            d.name as disease_name,
            diu.is_mydriatic as is_mydriatic,
            diu.is_pregraded as is_pregraded,

            -- Task Information
            gt.id as task_id,
            gt.uuid as task_uuid,
            gt.state as task_state,
            gt.created_at as task_created_at,

            -- Pivoted Grade Data with proper JOINs through disease_gradings
            -- Resident Grade
            resident_g.id as resident_grade_id,
            resident_dg.impression as resident_grade,
            resident_u.username as resident_grader,
            resident_g.created_at as resident_grade_time,
            resident_g.comment as resident_comment,
            resident_g.selected_features_json as resident_features,

            -- Resident2 Grade
            resident2_g.id as resident2_grade_id,
            resident2_dg.impression as resident2_grade,
            resident2_u.username as resident2_grader,
            resident2_g.created_at as resident2_grade_time,
            resident2_g.comment as resident2_comment,
            resident2_g.selected_features_json as resident2_features,

            -- Arbitrator Grade
            arbitrator_g.id as arbitrator_grade_id,
            arbitrator_dg.impression as arbitrator_grade,
            arbitrator_u.username as arbitrator_grader,
            arbitrator_g.created_at as arbitrator_grade_time,
            arbitrator_g.comment as arbitrator_comment,
            arbitrator_g.selected_features_json as arbitrator_features,

            -- Review Grade
            review_g.id as review_grade_id,
            review_dg.impression as review_grade,
            review_u.username as reviewer_name,
            review_g.created_at as review_grade_time,
            review_g.comment as review_comment,
            review_g.selected_features_json as review_features,

            -- AI Model Grades (dynamic columns - supporting multiple AI models)
            ai1_g.id as aimodel_1_grade_id,
            ai1_dg.impression as aimodel_1_grade,
            ai1_g.ai_model_name as aimodel_1_name,
            ai1_g.created_at as aimodel_1_time,
            ai1_g.selected_features_json as aimodel_1_features,

            ai2_g.id as aimodel_2_grade_id,
            ai2_dg.impression as aimodel_2_grade,
            ai2_g.ai_model_name as aimodel_2_name,
            ai2_g.created_at as aimodel_2_time,
            ai2_g.selected_features_json as aimodel_2_features,

            -- Additional AI grades (optional, can be extended)
            ai3_g.id as aimodel_3_grade_id,
            ai3_dg.impression as aimodel_3_grade,
            ai3_g.ai_model_name as aimodel_3_name,
            ai3_g.created_at as aimodel_3_time,
            ai3_g.selected_features_json as aimodel_3_features,

            -- Consensus Grade
            consensus_dg.impression as consensus_grade,
            c.method as consensus_method,
            decider_u.username as consensus_decider,
            c.decided_at as consensus_time,

            -- Additional Metadata
            gt.updated_at as last_updated

        FROM grading_tasks gt
        -- Image source handling
        LEFT JOIN encounter_files ef ON gt.encounter_file_id = ef.id
        LEFT JOIN direct_image_uploads diu ON gt.direct_image_upload_id = diu.id

        -- Patient encounter data
        LEFT JOIN patient_encounters pe ON ef.patient_encounter_id = pe.id

        -- Hospital/lab context
        LEFT JOIN hospitals h ON diu.hospital_id = h.id
        LEFT JOIN lab_units lu ON gt.lab_unit_id = lu.id
        LEFT JOIN cameras cam ON diu.camera_id = cam.id

        -- Filter for Diabetic Retinopathy specifically
        JOIN diseases d ON gt.disease_id = d.id AND d.name ILIKE '%retinopathy%'

        -- Pivoted grades with proper relationships through disease_gradings
        LEFT JOIN grades resident_g ON gt.id = resident_g.task_id AND resident_g.role_slot = 'resident'
        LEFT JOIN users resident_u ON resident_g.grader_user_id = resident_u.id
        LEFT JOIN disease_gradings resident_dg ON resident_g.disease_grading_id = resident_dg.id

        LEFT JOIN grades resident2_g ON gt.id = resident2_g.task_id AND resident2_g.role_slot = 'resident2'
        LEFT JOIN users resident2_u ON resident2_g.grader_user_id = resident2_u.id
        LEFT JOIN disease_gradings resident2_dg ON resident2_g.disease_grading_id = resident2_dg.id

        LEFT JOIN grades arbitrator_g ON gt.id = arbitrator_g.task_id AND arbitrator_g.role_slot = 'arbitrator'
        LEFT JOIN users arbitrator_u ON arbitrator_g.grader_user_id = arbitrator_u.id
        LEFT JOIN disease_gradings arbitrator_dg ON arbitrator_g.disease_grading_id = arbitrator_dg.id

        LEFT JOIN grades review_g ON gt.id = review_g.task_id AND review_g.role_slot = 'review'
        LEFT JOIN users review_u ON review_g.grader_user_id = review_u.id
        LEFT JOIN disease_gradings review_dg ON review_g.disease_grading_id = review_dg.id

        -- AI grades (limit to top 3 for performance, can be extended)
        LEFT JOIN grades ai1_g ON gt.id = ai1_g.task_id AND ai1_g.role_slot = 'ai'
        LEFT JOIN disease_gradings ai1_dg ON ai1_g.disease_grading_id = ai1_dg.id

        LEFT JOIN grades ai2_g ON gt.id = ai2_g.task_id AND ai2_g.role_slot = 'ai'
        AND ai2_g.id > ai1_g.id
        LEFT JOIN disease_gradings ai2_dg ON ai2_g.disease_grading_id = ai2_dg.id

        LEFT JOIN grades ai3_g ON gt.id = ai3_g.task_id AND ai3_g.role_slot = 'ai'
        AND ai3_g.id > ai2_g.id
        LEFT JOIN disease_gradings ai3_dg ON ai3_g.disease_grading_id = ai3_dg.id

        -- Consensus data
        LEFT JOIN consensus c ON gt.id = c.task_id
        LEFT JOIN users decider_u ON c.decided_by_user_id = decider_u.id
        LEFT JOIN disease_gradings consensus_dg ON c.final_disease_grading_id = consensus_dg.id

        WHERE (resident_g.id IS NOT NULL
               OR resident2_g.id IS NOT NULL
               OR arbitrator_g.id IS NOT NULL
               OR c.id IS NOT NULL
               OR ai1_g.id IS NOT NULL);
    """)

    # Create performance indexes
    op.execute("""
        -- Image identification indexes
        CREATE INDEX idx_mvw_dr_pivot_image_uuid ON mvw_diabetic_retinopathy_grading_pivot(image_uuid);
        CREATE INDEX idx_mvw_dr_pivot_image_source ON mvw_diabetic_retinopathy_grading_pivot(image_source);
        CREATE INDEX idx_mvw_dr_pivot_image_id ON mvw_diabetic_retinopathy_grading_pivot(image_id);

        -- Grade ID indexes for direct access
        CREATE INDEX idx_mvw_dr_pivot_resident_grade_id ON mvw_diabetic_retinopathy_grading_pivot(resident_grade_id);
        CREATE INDEX idx_mvw_dr_pivot_resident2_grade_id ON mvw_diabetic_retinopathy_grading_pivot(resident2_grade_id);
        CREATE INDEX idx_mvw_dr_pivot_arbitrator_grade_id ON mvw_diabetic_retinopathy_grading_pivot(arbitrator_grade_id);
        CREATE INDEX idx_mvw_dr_pivot_review_grade_id ON mvw_diabetic_retinopathy_grading_pivot(review_grade_id);
        CREATE INDEX idx_mvw_dr_pivot_aimodel_1_grade_id ON mvw_diabetic_retinopathy_grading_pivot(aimodel_1_grade_id);
        CREATE INDEX idx_mvw_dr_pivot_aimodel_2_grade_id ON mvw_diabetic_retinopathy_grading_pivot(aimodel_2_grade_id);

        -- Grade-specific indexes for analysis
        CREATE INDEX idx_mvw_dr_pivot_resident_grade ON mvw_diabetic_retinopathy_grading_pivot(resident_grade);
        CREATE INDEX idx_mvw_dr_pivot_resident2_grade ON mvw_diabetic_retinopathy_grading_pivot(resident2_grade);
        CREATE INDEX idx_mvw_dr_pivot_arbitrator_grade ON mvw_diabetic_retinopathy_grading_pivot(arbitrator_grade);
        CREATE INDEX idx_mvw_dr_pivot_consensus_grade ON mvw_diabetic_retinopathy_grading_pivot(consensus_grade);
        CREATE INDEX idx_mvw_dr_pivot_review_grade ON mvw_diabetic_retinopathy_grading_pivot(review_grade);

        -- AI model grade indexes
        CREATE INDEX idx_mvw_dr_pivot_aimodel_1_grade ON mvw_diabetic_retinopathy_grading_pivot(aimodel_1_grade);
        CREATE INDEX idx_mvw_dr_pivot_aimodel_2_grade ON mvw_diabetic_retinopathy_grading_pivot(aimodel_2_grade);

        -- Features JSON indexes for feature analysis
        CREATE INDEX idx_mvw_dr_pivot_resident_features ON mvw_diabetic_retinopathy_grading_pivot USING GIN((resident_features::jsonb));
        CREATE INDEX idx_mvw_dr_pivot_resident2_features ON mvw_diabetic_retinopathy_grading_pivot USING GIN((resident2_features::jsonb));
        CREATE INDEX idx_mvw_dr_pivot_arbitrator_features ON mvw_diabetic_retinopathy_grading_pivot USING GIN((arbitrator_features::jsonb));
        CREATE INDEX idx_mvw_dr_pivot_review_features ON mvw_diabetic_retinopathy_grading_pivot USING GIN((review_features::jsonb));
        CREATE INDEX idx_mvw_dr_pivot_aimodel_1_features ON mvw_diabetic_retinopathy_grading_pivot USING GIN((aimodel_1_features::jsonb));
        CREATE INDEX idx_mvw_dr_pivot_aimodel_2_features ON mvw_diabetic_retinopathy_grading_pivot USING GIN((aimodel_2_features::jsonb));

        -- Time-based indexes for trending analysis
        CREATE INDEX idx_mvw_dr_pivot_task_created ON mvw_diabetic_retinopathy_grading_pivot(task_created_at);
        CREATE INDEX idx_mvw_dr_pivot_consensus_time ON mvw_diabetic_retinopathy_grading_pivot(consensus_time);
        CREATE INDEX idx_mvw_dr_pivot_last_updated ON mvw_diabetic_retinopathy_grading_pivot(last_updated);

        -- DR-specific indexes
        CREATE INDEX idx_mvw_dr_pivot_disease_name ON mvw_diabetic_retinopathy_grading_pivot(disease_name);
        CREATE INDEX idx_mvw_dr_pivot_lab_unit ON mvw_diabetic_retinopathy_grading_pivot(lab_unit_name);
        CREATE INDEX idx_mvw_dr_pivot_hospital ON mvw_diabetic_retinopathy_grading_pivot(hospital_name);

        -- Grader analysis indexes
        CREATE INDEX idx_mvw_dr_pivot_resident_grader ON mvw_diabetic_retinopathy_grading_pivot(resident_grader);
        CREATE INDEX idx_mvw_dr_pivot_arbitrator_grader ON mvw_diabetic_retinopathy_grading_pivot(arbitrator_grader);
        CREATE INDEX idx_mvw_dr_pivot_consensus_decider ON mvw_diabetic_retinopathy_grading_pivot(consensus_decider);
    """)

    # Create refresh function for automated updates
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_diabetic_retinopathy_grading_pivot()
        RETURNS void AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW mvw_diabetic_retinopathy_grading_pivot;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the refresh function first
    op.execute("DROP FUNCTION IF EXISTS refresh_diabetic_retinopathy_grading_pivot();")

    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_consensus_decider;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_arbitrator_grader;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_resident_grader;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_hospital;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_lab_unit;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_disease_name;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_last_updated;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_consensus_time;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_task_created;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_aimodel_2_grade;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_aimodel_1_grade;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_review_grade;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_consensus_grade;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_arbitrator_grade;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_resident2_grade;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_resident_grade;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_aimodel_2_features;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_aimodel_1_features;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_review_features;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_arbitrator_features;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_resident2_features;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_resident_features;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_aimodel_2_grade_id;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_aimodel_1_grade_id;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_review_grade_id;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_arbitrator_grade_id;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_resident2_grade_id;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_resident_grade_id;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_image_id;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_image_source;")
    op.execute("DROP INDEX IF EXISTS idx_mvw_dr_pivot_image_uuid;")

    # Drop the materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_diabetic_retinopathy_grading_pivot;")
