from remedio_zip_uploads.routes import _available_ingest_modes


def test_zip_modes_are_limited_to_assigned_profile_flags():
    profiles = [
        {
            "upload_kinds": ["encounter_set"],
            "allow_remidio_zip_encounter_set": True,
            "allow_iitk_zip_encounter_set": False,
        }
    ]

    modes = _available_ingest_modes(profiles)

    assert [mode["value"] for mode in modes] == ["remidio_encounter_set"]


def test_zip_modes_include_each_explicitly_enabled_workflow():
    profiles = [
        {
            "upload_kinds": ["encounter_set"],
            "allow_remidio_zip_encounter_set": False,
            "allow_iitk_zip_encounter_set": True,
        },
        {"upload_kinds": ["remidio"]},
    ]

    modes = _available_ingest_modes(profiles)

    assert [mode["value"] for mode in modes] == [
        "iitk_encounter_set",
        "legacy_remidio",
    ]
