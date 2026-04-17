"""rebuild image listing v2 for final grade basis

Revision ID: 6f4b2d1c9a7e
Revises: 5b7d4c2a1e90
Create Date: 2026-03-18 10:30:00.000000

"""

from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from utils.mvw_image_listing_v2 import _build_mv_sql, _create_indexes_sql, _index_name, _mv_name


# revision identifiers, used by Alembic.
revision: str = "6f4b2d1c9a7e"
down_revision: Union[str, Sequence[str], None] = "5b7d4c2a1e90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _escape_literal(value: str) -> str:
    return (value or "").replace("'", "''")


def _ai_probability_expr() -> str:
    return "SUBSTRING(g.comment FROM 'AI probability:\\\\s*([0-9.]+)')"


def _legacy_build_mv_sql(mv_name: str, disease_id: int, disease_name: str) -> str:
    disease_name_literal = _escape_literal(disease_name)
    return f"""
    CREATE MATERIALIZED VIEW {mv_name} AS
    WITH base_images AS (
        SELECT
            diu.uuid AS image_uuid,
            diu.uuid AS direct_image_uuid,
            NULL::text AS encounter_file_uuid,
            diu.id AS direct_image_upload_id,
            NULL::integer AS encounter_file_id,
            NULL::integer AS patient_encounter_id,
            CASE WHEN diu.is_pregraded = TRUE THEN 'Pregraded' ELSE 'Direct' END AS upload_type,
            h.id AS hospital_id,
            h.name AS hospital_name,
            lu.name AS lab_unit_name,
            diu.camera_id AS camera_id,
            cam.name AS camera_name,
            a.name AS area_name,
            diu.filename AS direct_filename,
            diu.edited_filename AS direct_edited_filename,
            diu.folder_rel AS direct_folder_rel,
            NULL::text AS encounter_filename,
            NULL::date AS encounter_upload_date,
            COALESCE(diu.edited_filename, diu.filename) AS image_filename,
            diu.folder_rel AS image_folder_rel,
            FALSE AS is_set_based,
            NULL::date AS capture_date,
            diu.created_at AS upload_date_utc,
            div.verified_status AS direct_image_verified_status,
            NULL::text AS encounter_verified_status
        FROM direct_image_uploads diu
        LEFT JOIN direct_image_verifications div ON div.image_upload_id = diu.id
        LEFT JOIN hospitals h ON diu.hospital_id = h.id
        LEFT JOIN lab_units lu ON diu.lab_unit_id = lu.id
        LEFT JOIN cameras cam ON diu.camera_id = cam.id
        LEFT JOIN areas a ON diu.area_id = a.id

        UNION ALL

        SELECT
            ef.uuid AS image_uuid,
            NULL::text AS direct_image_uuid,
            ef.uuid AS encounter_file_uuid,
            NULL::integer AS direct_image_upload_id,
            ef.id AS encounter_file_id,
            ef.patient_encounter_id AS patient_encounter_id,
            'ZIP' AS upload_type,
            h.id AS hospital_id,
            h.name AS hospital_name,
            lu.name AS lab_unit_name,
            NULL::integer AS camera_id,
            NULL::text AS camera_name,
            NULL::text AS area_name,
            NULL::text AS direct_filename,
            NULL::text AS direct_edited_filename,
            NULL::text AS direct_folder_rel,
            ef.filename AS encounter_filename,
            zf.upload_date AS encounter_upload_date,
            ef.filename AS image_filename,
            NULL::text AS image_folder_rel,
            COALESCE(pe.is_set_based, FALSE) AS is_set_based,
            pe.capture_date_dt AS capture_date,
            zf.upload_date AS upload_date_utc,
            NULL::text AS direct_image_verified_status,
            pe.encounter_verified_status AS encounter_verified_status
        FROM encounter_files ef
        LEFT JOIN patient_encounters pe ON ef.patient_encounter_id = pe.id
        LEFT JOIN zip_files zf ON pe.zip_file_id = zf.id
        LEFT JOIN lab_units lu ON ef.lab_unit_id = lu.id
        LEFT JOIN hospitals h ON lu.hospital_id = h.id

        UNION ALL

        SELECT
            pe.uuid AS image_uuid,
            NULL::text AS direct_image_uuid,
            NULL::text AS encounter_file_uuid,
            NULL::integer AS direct_image_upload_id,
            NULL::integer AS encounter_file_id,
            pe.id AS patient_encounter_id,
            'SET' AS upload_type,
            h.id AS hospital_id,
            h.name AS hospital_name,
            lu.name AS lab_unit_name,
            NULL::integer AS camera_id,
            NULL::text AS camera_name,
            NULL::text AS area_name,
            NULL::text AS direct_filename,
            NULL::text AS direct_edited_filename,
            NULL::text AS direct_folder_rel,
            NULL::text AS encounter_filename,
            zf.upload_date AS encounter_upload_date,
            NULL::text AS image_filename,
            NULL::text AS image_folder_rel,
            COALESCE(pe.is_set_based, FALSE) AS is_set_based,
            pe.capture_date_dt AS capture_date,
            zf.upload_date AS upload_date_utc,
            NULL::text AS direct_image_verified_status,
            pe.encounter_verified_status AS encounter_verified_status
        FROM patient_encounters pe
        LEFT JOIN zip_files zf ON pe.zip_file_id = zf.id
        LEFT JOIN lab_units lu ON pe.lab_unit_id = lu.id
        LEFT JOIN hospitals h ON lu.hospital_id = h.id
        WHERE pe.is_set_based = TRUE
    ),
    disease_tasks AS (
        SELECT
            t.id AS task_id,
            t.uuid AS task_uuid,
            t.state AS task_state,
            t.created_at AS task_created_at,
            t.lab_unit_id,
            t.direct_image_upload_id,
            t.encounter_file_id,
            t.patient_encounter_id
        FROM grading_tasks t
        WHERE t.disease_id = {int(disease_id)}
    ),
    latest_role_grades AS (
        SELECT DISTINCT ON (g.task_id, g.role_slot)
            g.task_id,
            g.id AS grade_id,
            g.role_slot,
            g.grade_name,
            g.grade_description,
            g.comment,
            g.selected_features_json,
            g.ai_model_id,
            g.ai_model_name,
            g.ai_model_version,
            g.created_at
        FROM grades g
        JOIN disease_tasks t ON t.task_id = g.task_id
        ORDER BY g.task_id, g.role_slot, g.created_at DESC
    ),
    role_grade_pivot AS (
        SELECT
            task_id,
            MAX(grade_name) FILTER (WHERE role_slot = 'resident') AS resident_grade_name,
            MAX(grade_name) FILTER (WHERE role_slot = 'resident2') AS resident2_grade_name,
            MAX(grade_name) FILTER (WHERE role_slot = 'arbitrator') AS arbitrator_grade_name,
            MAX(grade_name) FILTER (WHERE role_slot = 'review') AS review_grade_name,
            MAX(grade_name) FILTER (WHERE role_slot = 'regrade_adj') AS regrade_adj_grade_name,
            MAX(comment) FILTER (WHERE role_slot = 'resident') AS resident_comment,
            MAX(comment) FILTER (WHERE role_slot = 'resident2') AS resident2_comment,
            MAX(comment) FILTER (WHERE role_slot = 'arbitrator') AS arbitrator_comment,
            MAX(comment) FILTER (WHERE role_slot = 'review') AS review_comment,
            MAX(comment) FILTER (WHERE role_slot = 'regrade_adj') AS regrade_adj_comment,
            MAX(selected_features_json) FILTER (WHERE role_slot = 'resident') AS resident_selected_features_json,
            MAX(selected_features_json) FILTER (WHERE role_slot = 'resident2') AS resident2_selected_features_json,
            MAX(selected_features_json) FILTER (WHERE role_slot = 'arbitrator') AS arbitrator_selected_features_json,
            MAX(selected_features_json) FILTER (WHERE role_slot = 'review') AS review_selected_features_json,
            MAX(selected_features_json) FILTER (WHERE role_slot = 'regrade_adj') AS regrade_adj_selected_features_json,
            MAX(CASE WHEN role_slot = 'resident' THEN 1 ELSE 0 END) AS has_resident,
            MAX(CASE WHEN role_slot = 'resident2' THEN 1 ELSE 0 END) AS has_resident2,
            MAX(CASE WHEN role_slot = 'arbitrator' THEN 1 ELSE 0 END) AS has_arbitrator,
            MAX(CASE WHEN role_slot = 'review' THEN 1 ELSE 0 END) AS has_review,
            MAX(CASE WHEN role_slot = 'regrade_adj' THEN 1 ELSE 0 END) AS has_regrade_adj
        FROM latest_role_grades
        GROUP BY task_id
    ),
    ai_latest AS (
        SELECT DISTINCT ON (g.task_id, g.ai_model_id)
            g.task_id,
            g.ai_model_id,
            g.id AS ai_grade_id,
            g.grade_name AS ai_grade_name,
            g.created_at AS ai_grade_created_at,
            g.comment AS ai_comment,
            g.selected_features_json AS ai_selected_features_json,
            g.ai_review_status,
            g.ai_review_comment,
            g.ai_reviewed_by_user_id,
            g.ai_reviewed_at,
            {_ai_probability_expr()} AS ai_probability
        FROM grades g
        JOIN disease_tasks t ON t.task_id = g.task_id
        WHERE g.role_slot = 'ai' AND g.ai_model_id IS NOT NULL
        ORDER BY g.task_id, g.ai_model_id, g.created_at DESC
    ),
    ai_map AS (
        SELECT
            a.task_id,
            TRUE AS has_ai,
            JSONB_OBJECT_AGG(
                a.ai_model_id::text,
                JSONB_BUILD_OBJECT(
                    'ai_model_id', a.ai_model_id,
                    'ai_model_name', m.name,
                    'ai_model_version', m.version,
                    'ai_grade_id', a.ai_grade_id,
                    'ai_grade_name', a.ai_grade_name,
                    'ai_grade_created_at', a.ai_grade_created_at,
                    'ai_comment', a.ai_comment,
                    'ai_selected_features', a.ai_selected_features_json,
                    'ai_review_status', a.ai_review_status,
                    'ai_review_comment', a.ai_review_comment,
                    'ai_reviewed_by_user_id', a.ai_reviewed_by_user_id,
                    'ai_reviewed_at', a.ai_reviewed_at,
                    'ai_probability', a.ai_probability
                )
            ) AS ai_models_json
        FROM ai_latest a
        JOIN ai_models m ON a.ai_model_id = m.id
        GROUP BY a.task_id
    )
    SELECT
        b.image_uuid,
        b.direct_image_uuid,
        b.encounter_file_uuid,
        b.direct_image_upload_id,
        b.encounter_file_id,
        b.patient_encounter_id,
        b.upload_type,
        b.hospital_id,
        b.hospital_name,
        b.lab_unit_name,
        b.camera_id,
        b.camera_name,
        b.area_name,
        b.direct_filename,
        b.direct_edited_filename,
        b.direct_folder_rel,
        b.encounter_filename,
        b.encounter_upload_date,
        b.image_filename,
        b.image_folder_rel,
        b.is_set_based,
        b.capture_date,
        b.upload_date_utc,
        b.direct_image_verified_status,
        b.encounter_verified_status,
        {int(disease_id)}::integer AS disease_id,
        '{disease_name_literal}'::text AS disease_name,
        dt.task_id,
        dt.task_uuid,
        dt.task_state,
        dt.task_created_at,
        dt.lab_unit_id AS task_lab_unit_id,
        (c.id IS NOT NULL) AS has_consensus,
        c.method AS consensus_type,
        dg.impression AS final_grade_name,
        rg.resident_grade_name,
        rg.resident2_grade_name,
        rg.arbitrator_grade_name,
        rg.review_grade_name,
        rg.regrade_adj_grade_name,
        rg.resident_comment,
        rg.resident2_comment,
        rg.arbitrator_comment,
        rg.review_comment,
        rg.regrade_adj_comment,
        rg.resident_selected_features_json,
        rg.resident2_selected_features_json,
        rg.arbitrator_selected_features_json,
        rg.review_selected_features_json,
        rg.regrade_adj_selected_features_json,
        COALESCE(rg.has_resident, 0) > 0 AS has_resident,
        COALESCE(rg.has_resident2, 0) > 0 AS has_resident2,
        COALESCE(rg.has_arbitrator, 0) > 0 AS has_arbitrator,
        COALESCE(rg.has_review, 0) > 0 AS has_review,
        COALESCE(rg.has_regrade_adj, 0) > 0 AS has_regrade_adj,
        COALESCE(am.has_ai, FALSE) AS has_ai,
        COALESCE(am.ai_models_json, '{{}}'::jsonb) AS ai_models_json,
        COALESCE(
            rg.regrade_adj_grade_name,
            rg.arbitrator_grade_name,
            CASE
                WHEN rg.resident_grade_name = rg.resident2_grade_name THEN rg.resident_grade_name
                ELSE NULL
            END
        ) AS final_impression,
        COALESCE(
            rg.review_grade_name,
            COALESCE(
                rg.regrade_adj_grade_name,
                rg.arbitrator_grade_name,
                CASE
                    WHEN rg.resident_grade_name = rg.resident2_grade_name THEN rg.resident_grade_name
                    ELSE NULL
                END
            )
        ) AS final_plus_review,
        CASE
            WHEN rg.resident_grade_name IS NULL OR rg.resident2_grade_name IS NULL THEN NULL
            WHEN rg.resident_grade_name = rg.resident2_grade_name THEN 'match'
            ELSE 'mismatch'
        END AS resident_vs_resident2
    FROM base_images b
    JOIN disease_tasks dt ON (
        (b.direct_image_upload_id IS NOT NULL AND dt.direct_image_upload_id = b.direct_image_upload_id) OR
        (b.encounter_file_id IS NOT NULL AND dt.encounter_file_id = b.encounter_file_id) OR
        (b.patient_encounter_id IS NOT NULL AND dt.patient_encounter_id = b.patient_encounter_id)
    )
    LEFT JOIN consensus c ON dt.task_id = c.task_id
    LEFT JOIN disease_gradings dg ON c.final_disease_grading_id = dg.id
    LEFT JOIN role_grade_pivot rg ON dt.task_id = rg.task_id
    LEFT JOIN ai_map am ON dt.task_id = am.task_id
    ;
    """


def _legacy_create_indexes_sql(mv_name: str) -> list[str]:
    return [
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'task_id')} ON {mv_name}(task_id);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'task_lab_unit_id')} ON {mv_name}(task_lab_unit_id);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'hospital_id')} ON {mv_name}(hospital_id);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'camera_id')} ON {mv_name}(camera_id);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'task_created_at')} ON {mv_name}(task_created_at);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'direct_image_verified_status')} ON {mv_name}(direct_image_verified_status);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'encounter_verified_status')} ON {mv_name}(encounter_verified_status);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'has_consensus')} ON {mv_name}(has_consensus);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'resident_vs_resident2')} ON {mv_name}(resident_vs_resident2);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'image_uuid')} ON {mv_name}(image_uuid);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'upload_type')} ON {mv_name}(upload_type);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'has_ai')} ON {mv_name}(has_ai);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'has_arbitrator')} ON {mv_name}(has_arbitrator);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'has_review')} ON {mv_name}(has_review);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'has_resident')} ON {mv_name}(has_resident);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'has_resident2')} ON {mv_name}(has_resident2);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'consensus_type')} ON {mv_name}(consensus_type);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'final_grade_name')} ON {mv_name}(final_grade_name);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'resident_grade_name')} ON {mv_name}(resident_grade_name);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'resident2_grade_name')} ON {mv_name}(resident2_grade_name);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'arbitrator_grade_name')} ON {mv_name}(arbitrator_grade_name);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'review_grade_name')} ON {mv_name}(review_grade_name);",
        f"CREATE INDEX IF NOT EXISTS {_index_name(mv_name, 'ai_models_json_gin')} ON {mv_name} USING GIN(ai_models_json);",
    ]


def _drop_existing_v2_views() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT matviewname FROM pg_matviews WHERE matviewname LIKE :pattern ORDER BY matviewname"),
        {"pattern": "mvw_image_listing_%_v2"},
    ).all()
    for (name,) in rows:
        if not re.fullmatch(r"[a-z0-9_]+", name):
            raise ValueError(f"Unsafe materialized view name: {name}")
        conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {name}"))


def _iter_diseases() -> list[tuple[int, str]]:
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, name FROM diseases ORDER BY id")).all()
    return [(int(row[0]), str(row[1])) for row in rows]


def _recreate_all(build_sql, build_indexes) -> None:
    conn = op.get_bind()
    for disease_id, disease_name in _iter_diseases():
        mv_name = _mv_name(disease_name, disease_id)
        conn.execute(text(build_sql(mv_name, disease_id, disease_name)))
        for idx_sql in build_indexes(mv_name):
            conn.execute(text(idx_sql))


def upgrade() -> None:
    """Rebuild per-disease image listing v2 materialized views with basis columns."""
    _drop_existing_v2_views()
    _recreate_all(_build_mv_sql, _create_indexes_sql)


def downgrade() -> None:
    """Rebuild per-disease image listing v2 materialized views without basis columns."""
    _drop_existing_v2_views()
    _recreate_all(_legacy_build_mv_sql, _legacy_create_indexes_sql)
