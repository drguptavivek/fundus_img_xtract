from pathlib import Path

from utils.mvw_image_listing_v2 import _build_mv_sql, _create_indexes_sql


def test_build_mv_sql_includes_basis_specific_final_impression_columns():
    sql = _build_mv_sql("mvw_image_listing_test_1_v2", 1, "DR")

    assert "AS final_impression_preference" in sql
    assert "AS final_impression_double_match" in sql
    assert "AS final_impression," in sql


def test_build_mv_sql_includes_encounter_set_images_without_multiplying_encounter_tasks():
    sql = _build_mv_sql(
        "mvw_image_listing_test_1_v2",
        1,
        "DR",
        include_encounter_set_images=True,
    )

    assert "FROM encounter_set_images esi" in sql
    assert "esi.id AS encounter_set_image_id" in sql
    assert "'EncounterSet' AS upload_type" in sql
    assert "dt.encounter_set_image_id = b.encounter_set_image_id" in sql
    assert "b.encounter_set_image_id IS NULL AND b.patient_encounter_id IS NOT NULL" in sql


def test_build_mv_sql_can_exclude_physical_encounter_set_rows_for_downgrade():
    sql = _build_mv_sql(
        "mvw_image_listing_test_1_v2",
        1,
        "DR",
        include_encounter_set_images=False,
    )

    assert "FROM encounter_set_images esi" not in sql


def test_image_listing_views_have_unique_task_key_and_concurrent_refresh():
    indexes = list(
        _create_indexes_sql(
            "mvw_image_listing_test_1_v2",
            include_encounter_set_images=True,
        )
    )
    module_source = Path("utils/mvw_image_listing_v2.py").read_text(encoding="utf-8")

    assert indexes[0] == (
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "mvw_image_listing_test_1_v2_task_id "
        "ON mvw_image_listing_test_1_v2(task_id);"
    )
    assert "REFRESH MATERIALIZED VIEW CONCURRENTLY {mv_name}" in module_source


def test_split_task_join_preserves_nulls_overlap_and_duplicate_rows(db_session):
    """Compare row multiplicities against OR semantics for every source kind."""
    from sqlalchemy import text

    sql = _build_mv_sql("unused", 1, "Glaucoma", include_encounter_set_images=True)
    branches = sql.split(", matched_images AS (", 1)[1].split(")\n    SELECT", 1)[0]
    query = """
        WITH base_images(image_uuid, direct_image_upload_id, encounter_file_id,
                         encounter_set_image_id, patient_encounter_id) AS (
            VALUES ('direct',1,NULL,NULL,NULL), ('zip',NULL,2,NULL,10),
                   ('set',NULL,NULL,NULL,10), ('physical',NULL,NULL,3,10),
                   ('unmatched',NULL,NULL,NULL,NULL),
                   ('duplicate',1,NULL,NULL,NULL), ('duplicate',1,NULL,NULL,NULL)
        ), disease_tasks(task_id, direct_image_upload_id, encounter_file_id,
                         encounter_set_image_id, patient_encounter_id) AS (
            VALUES (1,1,NULL,NULL,NULL), (2,NULL,2,NULL,10),
                   (3,NULL,NULL,3,10), (4,NULL,NULL,NULL,10),
                   (5,NULL,99,NULL,10), (6,NULL,NULL,NULL,NULL)
        ), optimized AS (
    """ + branches + """
        ), original AS (
            SELECT b.*, dt.task_id AS matched_task_id
            FROM base_images b JOIN disease_tasks dt ON
                dt.direct_image_upload_id=b.direct_image_upload_id OR
                dt.encounter_file_id=b.encounter_file_id OR
                dt.encounter_set_image_id=b.encounter_set_image_id OR
                (b.encounter_set_image_id IS NULL AND
                 dt.patient_encounter_id=b.patient_encounter_id)
        )
        SELECT * FROM ((SELECT * FROM original EXCEPT ALL SELECT * FROM optimized)
        UNION ALL (SELECT * FROM optimized EXCEPT ALL SELECT * FROM original)) differences
    """
    assert db_session.execute(text(query)).all() == []
