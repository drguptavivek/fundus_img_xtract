from utils.mvw_image_listing_v2 import _build_mv_sql


def test_build_mv_sql_includes_basis_specific_final_impression_columns():
    sql = _build_mv_sql("mvw_image_listing_test_1_v2", 1, "DR")

    assert "AS final_impression_preference" in sql
    assert "AS final_impression_double_match" in sql
    assert "AS final_impression," in sql
