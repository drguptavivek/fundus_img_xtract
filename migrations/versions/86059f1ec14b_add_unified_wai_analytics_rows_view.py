"""Add a unified WAI analytics rows view.

The existing materialized view contains task-scoped Wadhwani Glaucoma runs.
MadhuNetrAI is encounter-scoped and stores two target results per submitted
image, so expose both persistence models through one read-only analytics
contract without changing the established Glaucoma refresh path.

Revision ID: 86059f1ec14b
Revises: 32cbc2e0fe5f
Create Date: 2026-08-18 13:15:11.210302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86059f1ec14b'
down_revision: Union[str, Sequence[str], None] = '32cbc2e0fe5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the shared Glaucoma plus DR/DME analytics projection."""
    op.execute(
        """
        CREATE OR REPLACE VIEW wai_api_statistics_rows_v AS
        SELECT
            'glaucoma_task'::text AS inference_kind,
            'glaucoma_task:' || mv.inference_run_id::text AS inference_run_key,
            'glaucoma_task:' || mv.inference_run_id::text AS inference_row_key,
            mv.inference_run_id,
            mv.task_id,
            mv.task_uuid,
            mv.disease_id,
            mv.disease_name,
            mv.project_id,
            mv.project_title,
            mv.lab_unit_id,
            mv.hospital_id,
            mv.ai_model_id,
            mv.ai_model_name,
            mv.ai_model_version,
            mv.inference_status,
            mv.result_type,
            mv.is_latest_for_task_model,
            mv.image_source,
            mv.image_uuid,
            mv.image_filename,
            mv.normalized_patient_encounter_id,
            mv.patient_encounter_uuid,
            mv.encounter_name,
            mv.patient_identifier,
            mv.normalized_capture_date,
            mv.inference_created_at,
            mv.inference_finished_at,
            mv.ai_grade_name,
            mv.ai_probability,
            mv.api_prediction,
            mv.api_predicted_class,
            mv.api_predicted_class_name,
            mv.http_status,
            mv.error_code,
            mv.error_message
        FROM ai_inference_runs_mv AS mv

        UNION ALL

        SELECT
            'encounter_dr_dme'::text AS inference_kind,
            'encounter_dr_dme:' || run.id::text AS inference_run_key,
            'encounter_dr_dme:' || run.id::text || ':' || image_result.id::text || ':' || target.id::text
                AS inference_row_key,
            run.id AS inference_run_id,
            grading_task.id AS task_id,
            grading_task.uuid AS task_uuid,
            target.disease_id,
            disease.name AS disease_name,
            COALESCE(image.project_id, encounter.project_id) AS project_id,
            project.title AS project_title,
            COALESCE(encounter.lab_unit_id, grading_task.lab_unit_id) AS lab_unit_id,
            COALESCE(image.hospital_id, lab_unit.hospital_id) AS hospital_id,
            run.ai_model_id,
            ai_model.name AS ai_model_name,
            ai_model.version AS ai_model_version,
            CASE
                WHEN run.status IN ('presigning', 'uploading', 'submitting') THEN 'running'
                ELSE run.status
            END AS inference_status,
            CASE
                WHEN run.status NOT IN ('success', 'partial') THEN NULL
                WHEN lower(COALESCE(target_result.mapped_grade, '')) IN (
                    'mild dr', 'moderate npdr', 'severe npdr', 'pdr',
                    'dme present', 'm1 referable diabetic maculopathy'
                ) THEN 'positive'
                WHEN lower(COALESCE(target_result.mapped_grade, '')) IN (
                    'no dr', 'no dme', 'm0 no dme'
                ) THEN 'negative'
                ELSE 'inconclusive'
            END AS result_type,
            true AS is_latest_for_task_model,
            'encounter_set_image'::text AS image_source,
            image.uuid AS image_uuid,
            COALESCE(image.edited_filename, image.original_filename) AS image_filename,
            encounter.id AS normalized_patient_encounter_id,
            encounter.uuid AS patient_encounter_uuid,
            encounter.name AS encounter_name,
            encounter.patient_id AS patient_identifier,
            encounter.capture_date_dt AS normalized_capture_date,
            run.created_at AS inference_created_at,
            run.finished_at AS inference_finished_at,
            target_result.mapped_grade AS ai_grade_name,
            target_result.raw_score AS ai_probability,
            target_result.raw_label AS api_prediction,
            NULL::text AS api_predicted_class,
            target_result.raw_label AS api_predicted_class_name,
            run.http_status,
            run.error_code,
            run.error_message
        FROM encounter_ai_inference_runs AS run
        JOIN ai_models AS ai_model ON ai_model.id = run.ai_model_id
        JOIN patient_encounters AS encounter ON encounter.id = run.patient_encounter_id
        JOIN encounter_ai_image_results AS image_result ON image_result.run_id = run.id
        JOIN encounter_set_images AS image ON image.id = image_result.encounter_set_image_id
        JOIN encounter_ai_output_targets AS target
          ON target.ai_model_id = run.ai_model_id AND target.active = true
        JOIN diseases AS disease ON disease.id = target.disease_id
        LEFT JOIN encounter_ai_target_results AS target_result
          ON target_result.image_result_id = image_result.id
         AND target_result.output_target_id = target.id
        LEFT JOIN grades AS grade ON grade.id = target_result.grade_id
        LEFT JOIN grading_tasks AS grading_task ON grading_task.id = grade.task_id
        LEFT JOIN lab_units AS lab_unit ON lab_unit.id = encounter.lab_unit_id
        LEFT JOIN projects AS project ON project.id = COALESCE(image.project_id, encounter.project_id)
        """
    )


def downgrade() -> None:
    """Remove the unified analytics projection."""
    op.execute("DROP VIEW IF EXISTS wai_api_statistics_rows_v")
