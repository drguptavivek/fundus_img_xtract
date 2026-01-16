"""create_grading_data_materialized_view

Revision ID: ef304c5f8dd9
Revises: e3a73f43d244
Create Date: 2025-11-10 00:40:38.782569

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef304c5f8dd9'
down_revision: Union[str, Sequence[str], None] = 'e3a73f43d244'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create materialized view for comprehensive grading data analytics
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_grading_data_all")
    op.execute("""
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
            COALESCE(ef.filename, diu.original_filename) as filename,
            ef.eye_side as eye_side,
            ef.file_type as file_type,

            -- Context Data
            ef.patient_encounter_id as patient_encounter_id,
            h.name as hospital_name,
            h.id as hospital_id,
            cam.name as camera_name,
            cam.id as camera_id,
            lu.name as lab_unit_name,
            lu.id as lab_unit_id,
            a.name as area_name,
            a.id as area_id,

            -- Image-specific metadata
            diu.is_mydriatic as is_mydriatic,
            diu.is_pregraded as is_pregraded,
            diu.file_hash as file_hash,
            diu.content_hash as content_hash,
            diu.folder_rel as folder_rel,
            diu.edited_filename as edited_filename,
            diu.uploader_id as uploader_id,

            -- Task Information
            gt.id as task_id,
            gt.uuid as task_uuid,
            gt.disease_id,
            d.name as disease_name,
            gt.state as task_state,
            gt.created_at as task_created_at,
            gt.ad_hoc_id as ad_hoc_id,

            -- Individual Grade Details
            g.id as grade_id,
            g.role_slot as grade_role_slot,
            g.grader_user_id,
            grader.username as grader_username,
            grader.full_name as grader_full_name,
            g.grade_name as grade_name,
            g.grade_description as grade_description,
            g.comment as grade_comment,
            g.selected_features_json as selected_features_json,
            g.time_taken as grade_time_taken,
            g.start_time as grade_start_time,
            g.created_at as grade_created_at,

            -- AI Model Information
            g.ai_model_id,
            ai.name as ai_model_name,
            ai.version as ai_model_version,

            -- Complete Consensus Information
            c.id as consensus_id,
            c.method as consensus_method,
            c.final_disease_grading_id as consensus_final_grade_id,
            c.final_grade_name as consensus_final_grade_name,
            c.final_grade_description as consensus_final_grade_description,
            c.decided_by_user_id as consensus_decided_by_user_id,
            decider.username as consensus_decider_name,
            decider.full_name as consensus_decider_full_name,
            c.decided_at as consensus_created_at

        FROM grading_tasks gt
        -- Image source handling
        LEFT JOIN encounter_files ef ON gt.encounter_file_id = ef.id
        LEFT JOIN direct_image_uploads diu ON gt.direct_image_upload_id = diu.id

        -- Core grading relationships
        LEFT JOIN grades g ON gt.id = g.task_id
        LEFT JOIN consensus c ON gt.id = c.task_id

        -- Reference data joins
        LEFT JOIN diseases d ON gt.disease_id = d.id
        LEFT JOIN users grader ON g.grader_user_id = grader.id
        LEFT JOIN users decider ON c.decided_by_user_id = decider.id
        LEFT JOIN ai_models ai ON g.ai_model_id = ai.id

        -- Contextual data joins
        LEFT JOIN lab_units lu ON gt.lab_unit_id = lu.id
        LEFT JOIN hospitals h ON diu.hospital_id = h.id
        LEFT JOIN cameras cam ON diu.camera_id = cam.id
        LEFT JOIN areas a ON diu.area_id = a.id;
    """)

    # Create performance indexes on the materialized view
    # Image-related indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_image_uuid ON mvw_grading_data_all(image_uuid);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_image_source ON mvw_grading_data_all(image_source);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_image_id ON mvw_grading_data_all(image_id);")

    # Grade-related indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_task_id ON mvw_grading_data_all(task_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_grade_id ON mvw_grading_data_all(grade_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_grader_user ON mvw_grading_data_all(grader_user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_role_slot ON mvw_grading_data_all(grade_role_slot);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_disease ON mvw_grading_data_all(disease_id);")

    # Time-based indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_task_created ON mvw_grading_data_all(task_created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_grade_created ON mvw_grading_data_all(grade_created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_consensus_date ON mvw_grading_data_all(consensus_created_at);")

    # Consensus-specific indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_consensus_id ON mvw_grading_data_all(consensus_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_consensus_method ON mvw_grading_data_all(consensus_method);")

    # Context-related indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_hospital_id ON mvw_grading_data_all(hospital_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_lab_unit_id ON mvw_grading_data_all(lab_unit_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mvw_grading_camera_id ON mvw_grading_data_all(camera_id);")

    # Create refresh function for automated updates
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_grading_data_view()
        RETURNS void AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW CONCURRENTLY mvw_grading_data_all;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the refresh function first
    op.execute("DROP FUNCTION IF EXISTS refresh_grading_data_view();")

    # Drop the materialized view (indexes are dropped automatically)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_grading_data_all;")
