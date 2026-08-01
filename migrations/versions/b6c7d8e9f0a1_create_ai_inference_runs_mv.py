"""Create AI inference runs materialized view.

Revision ID: b6c7d8e9f0a1
Revises: a1b2c3d4e5fe
Create Date: 2026-08-01 00:00:00.000000
"""

from alembic import op


revision = "b6c7d8e9f0a1"
down_revision = "a1b2c3d4e5fe"
branch_labels = None
depends_on = None


VIEW_NAME = "ai_inference_runs_mv"


def upgrade() -> None:
    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {VIEW_NAME};")
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW {VIEW_NAME} AS
        WITH latest_ai_grade AS (
            SELECT DISTINCT ON (g.task_id, g.ai_model_id)
                g.task_id,
                g.ai_model_id,
                g.id AS ai_grade_id,
                g.disease_grading_id AS ai_disease_grading_id,
                g.grade_name AS ai_grade_name,
                g.comment AS ai_comment,
                g.selected_features_json AS ai_selected_features_json,
                g.ai_review_status,
                g.ai_review_comment,
                g.ai_reviewed_by_user_id,
                g.ai_reviewed_at,
                g.created_at AS ai_grade_created_at,
                g.updated_at AS ai_grade_updated_at,
                substring(g.comment from 'AI probability: ([0-9.]+)')::double precision AS ai_probability
            FROM grades g
            WHERE g.role_slot = 'ai'
              AND g.ai_model_id IS NOT NULL
            ORDER BY g.task_id, g.ai_model_id, g.created_at DESC, g.id DESC
        ),
        normalized_runs AS (
            SELECT
                r.id AS inference_run_id,
                r.task_id,
                r.ai_model_id,
                r.integration_id,
                r.requested_by_user_id,
                r.source AS inference_source,
                r.status AS inference_status,
                r.external_request_id,
                r.prediction_id,
                r.remote_filename,
                r.remote_content_type,
                r.http_status,
                r.request_manifest_json,
                r.initialize_response_json,
                r.execute_response_json,
                r.error_code,
                r.error_message,
                r.retry_count,
                r.created_at AS inference_created_at,
                r.started_at AS inference_started_at,
                r.finished_at AS inference_finished_at,
                r.updated_at AS inference_updated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY r.task_id, r.ai_model_id
                    ORDER BY r.created_at DESC, r.id DESC
                ) = 1 AS is_latest_for_task_model,
                (r.execute_response_json -> 'results' -> 0) AS result_json,
                (r.execute_response_json -> 'results' -> 0 ->> 'prediction') AS api_prediction,
                (r.execute_response_json -> 'results' -> 0 ->> 'predicted_class') AS api_predicted_class,
                (r.execute_response_json -> 'results' -> 0 ->> 'predicted_class_name') AS api_predicted_class_name,
                COALESCE(
                    NULLIF(r.prediction_id, ''),
                    NULLIF(r.execute_response_json ->> 'prediction_id', '')
                ) AS normalized_prediction_id
            FROM ai_inference_runs r
        )
        SELECT
            nr.inference_run_id,
            nr.task_id,
            gt.uuid AS task_uuid,
            gt.state AS task_state,
            gt.task_source,
            gt.grading_target_level,
            gt.disease_id,
            d.name AS disease_name,
            gt.lab_unit_id AS task_lab_unit_id,
            gt.created_at AS task_created_at,
            gt.updated_at AS task_updated_at,
            nr.ai_model_id,
            am.name AS ai_model_name,
            am.version AS ai_model_version,
            nr.integration_id,
            ami.provider AS integration_provider,
            ami.is_enabled AS integration_enabled,
            nr.requested_by_user_id,
            nr.inference_source,
            nr.inference_status,
            CASE
                WHEN nr.inference_status = 'success'
                 AND (
                    lower(COALESCE(lag.ai_grade_name, '')) IN ('glaucoma', 'referable', 'referrable', 'positive')
                    OR lower(COALESCE(nr.api_prediction, '')) IN ('referable', 'referrable', 'positive')
                    OR lower(COALESCE(nr.api_predicted_class_name, '')) IN ('referable', 'referrable', 'positive')
                    OR nr.api_predicted_class = '1'
                 )
                    THEN 'positive'
                WHEN nr.inference_status = 'success'
                 AND (
                    lower(COALESCE(lag.ai_grade_name, '')) IN ('normal', 'no glaucoma', 'negative', 'non-referrable', 'non-referable')
                    OR lower(COALESCE(nr.api_prediction, '')) IN ('normal', 'negative', 'non-referrable', 'non-referable')
                    OR lower(COALESCE(nr.api_predicted_class_name, '')) IN ('normal', 'negative', 'non-referrable', 'non-referable')
                    OR nr.api_predicted_class = '0'
                 )
                    THEN 'negative'
                WHEN nr.inference_status = 'success'
                    THEN 'inconclusive'
                ELSE NULL
            END AS result_type,
            nr.is_latest_for_task_model,
            nr.external_request_id,
            nr.normalized_prediction_id AS prediction_id,
            nr.remote_filename,
            nr.remote_content_type,
            nr.http_status,
            nr.api_prediction,
            nr.api_predicted_class,
            nr.api_predicted_class_name,
            nr.result_json,
            nr.request_manifest_json,
            nr.initialize_response_json,
            nr.execute_response_json,
            nr.error_code,
            nr.error_message,
            nr.retry_count,
            nr.inference_created_at,
            nr.inference_started_at,
            nr.inference_finished_at,
            nr.inference_updated_at,
            lag.ai_grade_id,
            lag.ai_disease_grading_id,
            lag.ai_grade_name,
            lag.ai_comment,
            lag.ai_selected_features_json,
            lag.ai_probability,
            lag.ai_review_status,
            lag.ai_review_comment,
            lag.ai_reviewed_by_user_id,
            lag.ai_reviewed_at,
            lag.ai_grade_created_at,
            lag.ai_grade_updated_at,
            gt.direct_image_upload_id,
            gt.encounter_file_id,
            gt.encounter_set_image_id,
            gt.patient_encounter_id,
            CASE
                WHEN gt.direct_image_upload_id IS NOT NULL THEN 'direct_image'
                WHEN gt.encounter_file_id IS NOT NULL THEN 'encounter_file'
                WHEN gt.encounter_set_image_id IS NOT NULL THEN 'encounter_set_image'
                WHEN gt.patient_encounter_id IS NOT NULL THEN 'encounter'
                ELSE 'unknown'
            END AS image_source,
            COALESCE(diu.uuid, ef.uuid, esi.uuid, pe.uuid) AS image_uuid,
            COALESCE(diu.filename, ef.filename, esi.edited_filename, esi.original_filename, pe.name) AS image_filename,
            COALESCE(esi.patient_encounter_id, ef.patient_encounter_id, gt.patient_encounter_id) AS normalized_patient_encounter_id,
            pe.uuid AS patient_encounter_uuid,
            pe.name AS encounter_name,
            pe.patient_id AS patient_identifier,
            pe.capture_date AS encounter_capture_date_text,
            pe.capture_date_dt AS capture_date,
            COALESCE(diu.created_at::date, pe.capture_date_dt) AS normalized_capture_date,
            COALESCE(diu.project_id, esi.project_id, ef.project_id, pe.project_id) AS project_id,
            p.title AS project_title,
            p.code AS project_code,
            COALESCE(diu.hospital_id, esi.hospital_id, ef.hospital_id) AS hospital_id,
            COALESCE(diu.lab_unit_id, ef.lab_unit_id, pe.lab_unit_id, gt.lab_unit_id) AS lab_unit_id,
            COALESCE(diu.camera_id, esi.camera_id, ef.camera_id) AS camera_id,
            COALESCE(diu.area_id, esi.area_id) AS area_id,
            esi.spatial_position AS encounter_set_spatial_position,
            ef.eye_side AS encounter_file_eye_side
        FROM normalized_runs nr
        JOIN grading_tasks gt ON gt.id = nr.task_id
        JOIN diseases d ON d.id = gt.disease_id
        JOIN ai_models am ON am.id = nr.ai_model_id
        LEFT JOIN ai_model_integrations ami ON ami.id = nr.integration_id
        LEFT JOIN latest_ai_grade lag ON lag.task_id = nr.task_id AND lag.ai_model_id = nr.ai_model_id
        LEFT JOIN direct_image_uploads diu ON diu.id = gt.direct_image_upload_id
        LEFT JOIN encounter_files ef ON ef.id = gt.encounter_file_id
        LEFT JOIN encounter_set_images esi ON esi.id = gt.encounter_set_image_id
        LEFT JOIN patient_encounters pe ON pe.id = COALESCE(esi.patient_encounter_id, ef.patient_encounter_id, gt.patient_encounter_id)
        LEFT JOIN projects p ON p.id = COALESCE(diu.project_id, esi.project_id, ef.project_id, pe.project_id)
        ;
        """
    )
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{VIEW_NAME}_pkey ON {VIEW_NAME}(inference_run_id);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_latest ON {VIEW_NAME}(is_latest_for_task_model);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_status ON {VIEW_NAME}(inference_status);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_result_type ON {VIEW_NAME}(result_type);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_disease ON {VIEW_NAME}(disease_id);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_project ON {VIEW_NAME}(project_id);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_model ON {VIEW_NAME}(ai_model_id);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_capture_date ON {VIEW_NAME}(normalized_capture_date);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_inference_created ON {VIEW_NAME}(inference_created_at);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_encounter ON {VIEW_NAME}(normalized_patient_encounter_id);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_image_uuid ON {VIEW_NAME}(image_uuid);")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{VIEW_NAME}_task_model ON {VIEW_NAME}(task_id, ai_model_id);")


def downgrade() -> None:
    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {VIEW_NAME};")
