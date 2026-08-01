from utils.mvw_image_listing_v2 import _build_mv_sql


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
