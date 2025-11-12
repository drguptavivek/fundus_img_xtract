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
    # Create comprehensive materialized view for image listing analytics
    op.execute("""
        CREATE MATERIALIZED VIEW mvw_image_listing_all AS
        SELECT
            -- Core identification
            diu.uuid as image_uuid,
            diu.uuid as image_upload_task_uuid,
            NULL as encounter_file_uuid,

            -- Upload type classification
            CASE WHEN diu.is_pregraded = TRUE THEN 'Pregraded' ELSE 'Direct' END as upload_type,

            -- Verification status
            CASE WHEN MAX(div.verified_status) = 'verified' THEN 1 ELSE 0 END as verified_status_direct,
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
            0 as additional_glaucoma_disease,

            -- Task configuration (will be updated in later CTEs)
            0 as has_dr_task,
            0 as has_glaucoma_task,
            0 as has_amd_task,

            -- Grading statistics (will be updated in later CTEs)
            0 as dr_grading_count,
            0 as glaucoma_grading_count,
            0 as amd_grading_count,
            0 as dr_ai_grading_count,
            0 as glaucoma_ai_grading_count,
            0 as amd_ai_grading_count,

            -- Consensus status (will be updated in later CTEs)
            0 as dr_consensus_status,
            0 as glaucoma_consensus_status,
            0 as amd_consensus_status,

            -- Detailed grading data (will be updated in later CTEs)
            '[]'::json as dr_grading_details_json,
            '[]'::json as glaucoma_grading_details_json,
            '[]'::json as amd_grading_details_json

        FROM direct_image_uploads diu
        LEFT JOIN direct_image_verifications div ON diu.id = div.image_upload_id
        LEFT JOIN hospitals h ON diu.hospital_id = h.id
        LEFT JOIN lab_units lu ON diu.lab_unit_id = lu.id
        LEFT JOIN cameras cam ON diu.camera_id = cam.id
        LEFT JOIN areas a ON diu.area_id = a.id
        LEFT JOIN diseases d ON diu.disease_id = d.id
        GROUP BY diu.uuid, diu.is_pregraded, diu.is_mydriatic, diu.created_at,
                 h.name, lu.name, cam.name, a.name, d.name

        UNION ALL

        SELECT
            -- Core identification
            ef.uuid as image_uuid,
            NULL as image_upload_task_uuid,
            ef.uuid as encounter_file_uuid,

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
            CASE WHEN pe.glaucoma_verified_status IS NOT NULL THEN 1 ELSE 0 END as additional_glaucoma_disease,

            -- Task configuration (will be updated in later CTEs)
            0 as has_dr_task,
            0 as has_glaucoma_task,
            0 as has_amd_task,

            -- Grading statistics (will be updated in later CTEs)
            0 as dr_grading_count,
            0 as glaucoma_grading_count,
            0 as amd_grading_count,
            0 as dr_ai_grading_count,
            0 as glaucoma_ai_grading_count,
            0 as amd_ai_grading_count,

            -- Consensus status (will be updated in later CTEs)
            0 as dr_consensus_status,
            0 as glaucoma_consensus_status,
            0 as amd_consensus_status,

            -- Detailed grading data (will be updated in later CTEs)
            '[]'::json as dr_grading_details_json,
            '[]'::json as glaucoma_grading_details_json,
            '[]'::json as amd_grading_details_json

        FROM encounter_files ef
        LEFT JOIN patient_encounters pe ON ef.patient_encounter_id = pe.id
        LEFT JOIN zip_files zf ON pe.zip_file_id = zf.id
        LEFT JOIN lab_units lu ON ef.lab_unit_id = lu.id;
    """)

    # Create minimal performance indexes on the materialized view
    # Core identification indexes
    op.execute("CREATE INDEX idx_image_listing_uuid ON mvw_image_listing_all(image_uuid);")

    # Location-based indexes
    op.execute("CREATE INDEX idx_image_listing_hospital ON mvw_image_listing_all(hospital_name);")
    op.execute("CREATE INDEX idx_image_listing_lab_unit ON mvw_image_listing_all(lab_unit_name);")

    # Date-based indexes
    op.execute("CREATE INDEX idx_image_listing_capture_date ON mvw_image_listing_all(capture_date);")
    op.execute("CREATE INDEX idx_image_listing_upload_date ON mvw_image_listing_all(upload_date_utc);")

    # Classification index
    op.execute("CREATE INDEX idx_image_listing_upload_type ON mvw_image_listing_all(upload_type);")

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

    # Drop the materialized view (indexes are dropped automatically)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_image_listing_all;")