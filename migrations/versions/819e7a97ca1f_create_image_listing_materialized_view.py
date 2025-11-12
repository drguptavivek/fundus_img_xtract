"""Create image listing materialized view

Revision ID: 819e7a97ca1f
Revises: bd1d20ea7d83
Create Date: 2025-11-12 02:29:14.691632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '819e7a97ca1f'
down_revision: Union[str, Sequence[str], None] = 'bd1d20ea7d83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create comprehensive materialized view for image listing analytics with real data
    op.execute("""
        CREATE MATERIALIZED VIEW mvw_image_listing_all AS
        WITH base_images AS (
            -- Base image data from both sources
            SELECT
                -- Core identification
                diu.uuid as image_uuid,
                diu.uuid as image_upload_task_uuid,
                NULL as encounter_file_uuid,
                diu.id as direct_image_upload_id,
                NULL as encounter_file_id,

                -- Upload type classification
                CASE WHEN diu.is_pregraded = TRUE THEN 'Pregraded' ELSE 'Direct' END as upload_type,

                -- Verification status
                CASE WHEN EXISTS(SELECT 1 FROM direct_image_verifications div WHERE div.image_upload_id = diu.id AND div.verified_status = 'verified') THEN 1 ELSE 0 END as verified_status_direct,
                0 as verified_status_zip,

                -- Pregraded status
                diu.is_pregraded,

                -- Report availability (0 for direct uploads)
                0 as has_glaucoma_report,
                0 as has_dr_report,

                -- Location and metadata
                h.name as hospital_name,
                lu.name as lab_unit_name,
                cam.name as camera_name,
                a.name as area_name,
                diu.is_mydriatic,

                -- Dates
                NULL as capture_date,
                diu.created_at as upload_date_utc,

                -- Disease configuration
                d.name as original_disease_uploaded,
                0 as additional_glaucoma_disease

            FROM direct_image_uploads diu
            LEFT JOIN direct_image_verifications div ON diu.id = div.image_upload_id
            LEFT JOIN hospitals h ON diu.hospital_id = h.id
            LEFT JOIN lab_units lu ON diu.lab_unit_id = lu.id
            LEFT JOIN cameras cam ON diu.camera_id = cam.id
            LEFT JOIN areas a ON diu.area_id = a.id
            LEFT JOIN diseases d ON diu.disease_id = d.id

            UNION ALL

            SELECT
                -- Core identification
                ef.uuid as image_uuid,
                NULL as image_upload_task_uuid,
                ef.uuid as encounter_file_uuid,
                NULL as direct_image_upload_id,
                ef.id as encounter_file_id,

                -- Upload type classification
                'ZIP' as upload_type,

                -- Verification status
                0 as verified_status_direct,
                CASE WHEN pe.encounter_verified_status = 'verified' THEN 1 ELSE 0 END as verified_status_zip,

                -- Pregraded status
                FALSE as is_pregraded,

                -- Report availability
                CASE WHEN pe.glaucoma_verified_status IS NOT NULL THEN 1 ELSE 0 END as has_glaucoma_report,
                CASE WHEN pe.dr_verified_status IS NOT NULL THEN 1 ELSE 0 END as has_dr_report,

                -- Location and metadata
                NULL as hospital_name, -- ZIP uploads don't have hospital info
                lu.name as lab_unit_name,
                NULL as camera_name, -- ZIP uploads don't have camera info
                NULL as area_name, -- ZIP uploads don't have area info
                FALSE as is_mydriatic,

                -- Dates
                pe.capture_date_dt as capture_date,
                zf.upload_date as upload_date_utc,

                -- Disease configuration
                'DR' as original_disease_uploaded, -- ZIP uploads are always DR primary
                CASE WHEN pe.glaucoma_verified_status IS NOT NULL THEN 1 ELSE 0 END as additional_glaucoma_disease

            FROM encounter_files ef
            LEFT JOIN patient_encounters pe ON ef.patient_encounter_id = pe.id
            LEFT JOIN zip_files zf ON pe.zip_file_id = zf.id
            LEFT JOIN lab_units lu ON ef.lab_unit_id = lu.id
        ),
        task_data AS (
            -- Aggregate task and grading data per image
            SELECT
                bi.image_uuid,

                -- Task configuration counts
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%diabetic%' OR name ILIKE '%dr%') THEN 1 END) as has_dr_task,
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%glaucoma%') THEN 1 END) as has_glaucoma_task,
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%macular%' OR name ILIKE '%amd%') THEN 1 END) as has_amd_task,

                -- DR grading statistics
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%diabetic%' OR name ILIKE '%dr%') AND d_grade.role_slot = 'resident' THEN 1 END) as dr_grading_count,
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%diabetic%' OR name ILIKE '%dr%') AND d_grade.role_slot = 'ai' THEN 1 END) as dr_ai_grading_count,

                -- Glaucoma grading statistics
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%glaucoma%') AND d_grade.role_slot = 'resident' THEN 1 END) as glaucoma_grading_count,
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%glaucoma%') AND d_grade.role_slot = 'ai' THEN 1 END) as glaucoma_ai_grading_count,

                -- AMD grading statistics
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%macular%' OR name ILIKE '%amd%') AND d_grade.role_slot = 'resident' THEN 1 END) as amd_grading_count,
                COUNT(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%macular%' OR name ILIKE '%amd%') AND d_grade.role_slot = 'ai' THEN 1 END) as amd_ai_grading_count,

                -- Consensus status
                MAX(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%diabetic%' OR name ILIKE '%dr%') AND d_consensus.id IS NOT NULL THEN 1 ELSE 0 END) as dr_consensus_status,
                MAX(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%glaucoma%') AND d_consensus.id IS NOT NULL THEN 1 ELSE 0 END) as glaucoma_consensus_status,
                MAX(CASE WHEN d_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%macular%' OR name ILIKE '%amd%') AND d_consensus.id IS NOT NULL THEN 1 ELSE 0 END) as amd_consensus_status

            FROM base_images bi
            LEFT JOIN grading_tasks d_task ON (
                (bi.direct_image_upload_id IS NOT NULL AND d_task.direct_image_upload_id = bi.direct_image_upload_id) OR
                (bi.encounter_file_id IS NOT NULL AND d_task.encounter_file_id = bi.encounter_file_id)
            )
            LEFT JOIN grades d_grade ON d_task.id = d_grade.task_id
            LEFT JOIN consensus d_consensus ON d_task.id = d_consensus.task_id
            GROUP BY bi.image_uuid
        ),
        grading_details AS (
            -- Aggregate grading details as JSON per disease
            SELECT
                bi.image_uuid,

                -- DR grading details JSON
                COALESCE(
                    JSON_AGG(
                        JSON_BUILD_OBJECT(
                            'grade_id', dr_g.id,
                            'role_slot', dr_g.role_slot,
                            'grader_user_id', dr_g.grader_user_id,
                            'grade_name', dr_g.grade_name,
                            'grade_description', dr_g.grade_description,
                            'comment', dr_g.comment,
                            'selected_features', dr_g.selected_features_json::json,
                            'ai_model_id', dr_g.ai_model_id,
                            'ai_model_name', dr_ai.name,
                            'created_at', dr_g.created_at
                        )
                    ) FILTER (WHERE dr_g.id IS NOT NULL),
                    '[]'::json
                ) as dr_grading_details_json,

                -- Glaucoma grading details JSON
                COALESCE(
                    JSON_AGG(
                        JSON_BUILD_OBJECT(
                            'grade_id', gl_g.id,
                            'role_slot', gl_g.role_slot,
                            'grader_user_id', gl_g.grader_user_id,
                            'grade_name', gl_g.grade_name,
                            'grade_description', gl_g.grade_description,
                            'comment', gl_g.comment,
                            'selected_features', gl_g.selected_features_json::json,
                            'ai_model_id', gl_g.ai_model_id,
                            'ai_model_name', gl_ai.name,
                            'created_at', gl_g.created_at
                        )
                    ) FILTER (WHERE gl_g.id IS NOT NULL),
                    '[]'::json
                ) as glaucoma_grading_details_json,

                -- AMD grading details JSON
                COALESCE(
                    JSON_AGG(
                        JSON_BUILD_OBJECT(
                            'grade_id', amd_g.id,
                            'role_slot', amd_g.role_slot,
                            'grader_user_id', amd_g.grader_user_id,
                            'grade_name', amd_g.grade_name,
                            'grade_description', amd_g.grade_description,
                            'comment', amd_g.comment,
                            'selected_features', amd_g.selected_features_json::json,
                            'ai_model_id', amd_g.ai_model_id,
                            'ai_model_name', amd_ai.name,
                            'created_at', amd_g.created_at
                        )
                    ) FILTER (WHERE amd_g.id IS NOT NULL),
                    '[]'::json
                ) as amd_grading_details_json

            FROM base_images bi
            LEFT JOIN grading_tasks dr_task ON (
                (bi.direct_image_upload_id IS NOT NULL AND dr_task.direct_image_upload_id = bi.direct_image_upload_id) OR
                (bi.encounter_file_id IS NOT NULL AND dr_task.encounter_file_id = bi.encounter_file_id)
            ) AND dr_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%diabetic%' OR name ILIKE '%dr%')
            LEFT JOIN grades dr_g ON dr_task.id = dr_g.task_id
            LEFT JOIN ai_models dr_ai ON dr_g.ai_model_id = dr_ai.id

            LEFT JOIN grading_tasks gl_task ON (
                (bi.direct_image_upload_id IS NOT NULL AND gl_task.direct_image_upload_id = bi.direct_image_upload_id) OR
                (bi.encounter_file_id IS NOT NULL AND gl_task.encounter_file_id = bi.encounter_file_id)
            ) AND gl_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%glaucoma%')
            LEFT JOIN grades gl_g ON gl_task.id = gl_g.task_id
            LEFT JOIN ai_models gl_ai ON gl_g.ai_model_id = gl_ai.id

            LEFT JOIN grading_tasks amd_task ON (
                (bi.direct_image_upload_id IS NOT NULL AND amd_task.direct_image_upload_id = bi.direct_image_upload_id) OR
                (bi.encounter_file_id IS NOT NULL AND amd_task.encounter_file_id = bi.encounter_file_id)
            ) AND amd_task.disease_id IN (SELECT id FROM diseases WHERE name ILIKE '%macular%' OR name ILIKE '%amd%')
            LEFT JOIN grades amd_g ON amd_task.id = amd_g.task_id
            LEFT JOIN ai_models amd_ai ON amd_g.ai_model_id = amd_ai.id

            GROUP BY bi.image_uuid
        )

        -- Final result combining all data
        SELECT
            bi.*,
            COALESCE(td.has_dr_task, 0) as has_dr_task,
            COALESCE(td.has_glaucoma_task, 0) as has_glaucoma_task,
            COALESCE(td.has_amd_task, 0) as has_amd_task,
            COALESCE(td.dr_grading_count, 0) as dr_grading_count,
            COALESCE(td.glaucoma_grading_count, 0) as glaucoma_grading_count,
            COALESCE(td.amd_grading_count, 0) as amd_grading_count,
            COALESCE(td.dr_ai_grading_count, 0) as dr_ai_grading_count,
            COALESCE(td.glaucoma_ai_grading_count, 0) as glaucoma_ai_grading_count,
            COALESCE(td.amd_ai_grading_count, 0) as amd_ai_grading_count,
            COALESCE(td.dr_consensus_status, 0) as dr_consensus_status,
            COALESCE(td.glaucoma_consensus_status, 0) as glaucoma_consensus_status,
            COALESCE(td.amd_consensus_status, 0) as amd_consensus_status,
            gd.dr_grading_details_json,
            gd.glaucoma_grading_details_json,
            gd.amd_grading_details_json

        FROM base_images bi
        LEFT JOIN task_data td ON bi.image_uuid = td.image_uuid
        LEFT JOIN grading_details gd ON bi.image_uuid = gd.image_uuid;
    """)

    # Create comprehensive performance indexes on the materialized view
    # Core identification indexes
    op.execute("CREATE INDEX idx_image_listing_uuid ON mvw_image_listing_all(image_uuid);")
    op.execute("CREATE INDEX idx_image_listing_upload_task_uuid ON mvw_image_listing_all(image_upload_task_uuid);")
    op.execute("CREATE INDEX idx_image_listing_encounter_file_uuid ON mvw_image_listing_all(encounter_file_uuid);")

    # Location-based indexes
    op.execute("CREATE INDEX idx_image_listing_hospital ON mvw_image_listing_all(hospital_name);")
    op.execute("CREATE INDEX idx_image_listing_lab_unit ON mvw_image_listing_all(lab_unit_name);")
    op.execute("CREATE INDEX idx_image_listing_camera ON mvw_image_listing_all(camera_name);")
    op.execute("CREATE INDEX idx_image_listing_area ON mvw_image_listing_all(area_name);")

    # Date-based indexes
    op.execute("CREATE INDEX idx_image_listing_capture_date ON mvw_image_listing_all(capture_date);")
    op.execute("CREATE INDEX idx_image_listing_upload_date ON mvw_image_listing_all(upload_date_utc);")

    # Classification indexes
    op.execute("CREATE INDEX idx_image_listing_upload_type ON mvw_image_listing_all(upload_type);")
    op.execute("CREATE INDEX idx_image_listing_original_disease ON mvw_image_listing_all(original_disease_uploaded);")
    op.execute("CREATE INDEX idx_image_listing_verification_direct ON mvw_image_listing_all(verified_status_direct);")
    op.execute("CREATE INDEX idx_image_listing_verification_zip ON mvw_image_listing_all(verified_status_zip);")

    # Task and grading count indexes for analytics
    op.execute("CREATE INDEX idx_image_listing_has_dr_task ON mvw_image_listing_all(has_dr_task);")
    op.execute("CREATE INDEX idx_image_listing_has_glaucoma_task ON mvw_image_listing_all(has_glaucoma_task);")
    op.execute("CREATE INDEX idx_image_listing_has_amd_task ON mvw_image_listing_all(has_amd_task);")

    # Grading count indexes
    op.execute("CREATE INDEX idx_image_listing_dr_grading_count ON mvw_image_listing_all(dr_grading_count);")
    op.execute("CREATE INDEX idx_image_listing_glaucoma_grading_count ON mvw_image_listing_all(glaucoma_grading_count);")
    op.execute("CREATE INDEX idx_image_listing_amd_grading_count ON mvw_image_listing_all(amd_grading_count);")

    # AI grading count indexes
    op.execute("CREATE INDEX idx_image_listing_dr_ai_grading_count ON mvw_image_listing_all(dr_ai_grading_count);")
    op.execute("CREATE INDEX idx_image_listing_glaucoma_ai_grading_count ON mvw_image_listing_all(glaucoma_ai_grading_count);")
    op.execute("CREATE INDEX idx_image_listing_amd_ai_grading_count ON mvw_image_listing_all(amd_ai_grading_count);")

    # Consensus status indexes
    op.execute("CREATE INDEX idx_image_listing_dr_consensus ON mvw_image_listing_all(dr_consensus_status);")
    op.execute("CREATE INDEX idx_image_listing_glaucoma_consensus ON mvw_image_listing_all(glaucoma_consensus_status);")
    op.execute("CREATE INDEX idx_image_listing_amd_consensus ON mvw_image_listing_all(amd_consensus_status);")

    # GIN indexes for JSONB columns to support JSON queries
    op.execute("CREATE INDEX idx_image_listing_dr_grading_details_json ON mvw_image_listing_all USING GIN((dr_grading_details_json::jsonb));")
    op.execute("CREATE INDEX idx_image_listing_glaucoma_grading_details_json ON mvw_image_listing_all USING GIN((glaucoma_grading_details_json::jsonb));")
    op.execute("CREATE INDEX idx_image_listing_amd_grading_details_json ON mvw_image_listing_all USING GIN((amd_grading_details_json::jsonb));")

    # Composite indexes for common query patterns
    op.execute("CREATE INDEX idx_image_listing_composite_upload_date_type ON mvw_image_listing_all(upload_date_utc, upload_type);")
    op.execute("CREATE INDEX idx_image_listing_composite_disease_tasks ON mvw_image_listing_all(original_disease_uploaded, has_dr_task, has_glaucoma_task, has_amd_task);")
    op.execute("CREATE INDEX idx_image_listing_composite_lab_unit_date ON mvw_image_listing_all(lab_unit_name, upload_date_utc);")

    # Create refresh function for automated updates
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_image_listing_all()
        RETURNS void AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW mvw_image_listing_all;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the refresh function first
    op.execute("DROP FUNCTION IF EXISTS refresh_image_listing_all();")

    # Drop indexes in reverse order of creation (composite indexes first)
    op.execute("DROP INDEX IF EXISTS idx_image_listing_composite_lab_unit_date;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_composite_disease_tasks;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_composite_upload_date_type;")

    # Drop GIN indexes for JSONB columns
    op.execute("DROP INDEX IF EXISTS idx_image_listing_amd_grading_details_json;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_glaucoma_grading_details_json;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_dr_grading_details_json;")

    # Drop consensus status indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_amd_consensus;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_glaucoma_consensus;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_dr_consensus;")

    # Drop AI grading count indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_amd_ai_grading_count;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_glaucoma_ai_grading_count;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_dr_ai_grading_count;")

    # Drop grading count indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_amd_grading_count;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_glaucoma_grading_count;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_dr_grading_count;")

    # Drop task and grading count indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_has_amd_task;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_has_glaucoma_task;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_has_dr_task;")

    # Drop classification indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_verification_zip;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_verification_direct;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_original_disease;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_upload_type;")

    # Drop date-based indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_upload_date;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_capture_date;")

    # Drop location-based indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_area;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_camera;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_lab_unit;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_hospital;")

    # Drop core identification indexes
    op.execute("DROP INDEX IF EXISTS idx_image_listing_encounter_file_uuid;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_upload_task_uuid;")
    op.execute("DROP INDEX IF EXISTS idx_image_listing_uuid;")

    # Drop the materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_image_listing_all;")