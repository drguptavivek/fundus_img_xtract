from home import _filter_disease_rows_with_existing_v2_views


def test_filter_disease_rows_with_existing_v2_views_skips_missing_views():
    disease_rows = [
        (1, "Glaucoma"),
        (2, "DR"),
        (8, "AMD"),
    ]

    existing_mv_names = {
        "mvw_image_listing_glaucoma_1_v2",
        "mvw_image_listing_dr_2_v2",
    }

    assert _filter_disease_rows_with_existing_v2_views(disease_rows, existing_mv_names) == [
        (1, "Glaucoma"),
        (2, "DR"),
    ]
