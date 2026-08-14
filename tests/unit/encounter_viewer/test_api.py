from models import DiabeticRetinopathyReport, EncounterSetImage
from tests.helpers.test_factories import TestDataFactory


def _hospital_a_user(db_session, hospital_data, fixture_user):
    """Normalize legacy fixture hospital IDs to the seeded hospital lineage."""
    user = db_session.merge(fixture_user)
    user.hospital_id = hospital_data["hospital_a"]["hospital"].id
    db_session.flush()
    return user


def _encounter_with_image(db_session, lab_unit_id, *, patient_id="SECRET-MRN", name="Secret Patient"):
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=lab_unit_id,
        patient_id=patient_id,
        name=name,
    )
    image = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab_unit_id,
    )
    image.eye_side = "right"
    image.centering = "disc"
    db_session.flush()
    return encounter, image


def test_encounter_viewer_json_is_non_pii_and_uses_authenticated_media(
    auth_client, hospital_data, hosp_a_data_manager, db_session
):
    lab = hospital_data["hospital_a"]["lab_units"][0]
    encounter, image = _encounter_with_image(db_session, lab.id)
    db_session.add_all([
        DiabeticRetinopathyReport(
            patient_encounter_id=encounter.id,
            result="VISIBLE-REMIDIO-RESULT",
        ),
        DiabeticRetinopathyReport(
            patient_encounter_id=encounter.id,
            result="VISIBLE-REMIDIO-RESULT",
        ),
    ])
    db_session.flush()
    user = _hospital_a_user(db_session, hospital_data, hosp_a_data_manager)
    client = auth_client(user)

    response = client.get(f"/api/encounter-viewer/encounters/{encounter.id}")

    assert response.status_code == 200
    payload = response.get_json()
    serialized = response.get_data(as_text=True)
    assert payload["schema_version"] == 2
    assert payload["images"][0]["laterality"] == "OD"
    assert payload["images"][0]["focus"] == "disc"
    assert payload["images"][0]["media_url"] == f"/media/img/{image.uuid}"
    assert payload["images"][0]["thumbnail_url"] == f"/media/img/{image.uuid}/thumbnail"
    assert payload["inferences"][0]["result"] == "VISIBLE-REMIDIO-RESULT"
    assert payload["inferences"][0]["count"] == 2
    assert "SECRET-MRN" not in serialized
    assert "Secret Patient" not in serialized
    assert response.headers["Cache-Control"] == "private, no-store"


def test_encounter_viewer_htmx_returns_reusable_partial(
    auth_client, hospital_data, hosp_a_data_manager, db_session, core_test_data
):
    lab = hospital_data["hospital_a"]["lab_units"][0]
    encounter, image = _encounter_with_image(db_session, lab.id)
    TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=lab.id,
        disease_id=core_test_data["glaucoma"].id,
        encounter_file_id=image.id,
    )
    client = auth_client(_hospital_a_user(db_session, hospital_data, hosp_a_data_manager))

    response = client.get(
        f"/api/encounter-viewer/encounters/{encounter.id}",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-uev-root' in html
    assert 'data-uev-open-fullscreen' in html
    assert f"Encounter evidence · {encounter.id}" in html
    assert "Resident 2" in html
    assert "Regrade adjudicator" in html
    assert "Not submitted" in html
    assert f"/media/img/{image.uuid}" in html
    assert "SECRET-MRN" not in html


def test_browse_role_does_not_receive_clinical_result_contract(
    auth_client, hospital_data, hosp_a_optometrist, db_session
):
    lab = hospital_data["hospital_a"]["lab_units"][0]
    encounter, _ = _encounter_with_image(db_session, lab.id)
    db_session.add(DiabeticRetinopathyReport(
        patient_encounter_id=encounter.id,
        result="HIDDEN-REMIDIO-RESULT",
    ))
    db_session.flush()
    user = _hospital_a_user(db_session, hospital_data, hosp_a_optometrist)
    client = auth_client(user)

    response = client.get(f"/api/encounter-viewer/encounters/{encounter.id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["can_view_clinical_results"] is False
    assert payload["encounter_targets"] == []
    assert payload["inferences"] == []
    assert all(image["targets"] == [] for image in payload["images"])
    assert "HIDDEN-REMIDIO-RESULT" not in response.get_data(as_text=True)


def test_encounter_viewer_cross_hospital_is_non_disclosing(
    auth_client, hospital_data, hosp_a_data_manager, db_session
):
    lab_b = hospital_data["hospital_b"]["lab_units"][0]
    encounter, _ = _encounter_with_image(db_session, lab_b.id)
    client = auth_client(_hospital_a_user(db_session, hospital_data, hosp_a_data_manager))

    response = client.get(f"/api/encounter-viewer/encounters/{encounter.id}")

    assert response.status_code == 404


def test_encounter_set_normalizes_non_pii_images_and_omits_pii_assets(
    auth_client, hospital_data, hosp_a_data_manager, db_session
):
    lab = hospital_data["hospital_a"]["lab_units"][0]
    encounter = TestDataFactory.create_patient_encounter(db_session, lab_unit_id=lab.id)
    encounter.is_set_based = True
    clinical = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="clinical.jpg",
        folder_rel="files/test",
        is_pii=False,
        metadata_json={"laterality": "left", "focus": "macula"},
    )
    pii = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=2,
        original_filename="pii.jpg",
        folder_rel="files/test",
        is_pii=True,
    )
    db_session.add_all([clinical, pii])
    db_session.flush()
    client = auth_client(_hospital_a_user(db_session, hospital_data, hosp_a_data_manager))

    response = client.get(f"/api/encounter-viewer/encounters/{encounter.id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["source_kind"] == "encounter_set"
    assert [image["uuid"] for image in payload["images"]] == [clinical.uuid]
    assert payload["images"][0]["laterality"] == "OS"
    assert payload["images"][0]["focus"] == "macula"
    assert pii.uuid not in response.get_data(as_text=True)


def test_direct_image_uses_same_viewer_contract(
    auth_client, hospital_data, hosp_a_data_manager, db_session, core_test_data
):
    lab = hospital_data["hospital_a"]["lab_units"][0]
    user = _hospital_a_user(db_session, hospital_data, hosp_a_data_manager)
    image = TestDataFactory.create_direct_image_upload(
        db_session,
        lab_unit_id=lab.id,
        uploader_id=user.id,
        hospital_id=lab.hospital_id,
        camera_id=core_test_data["camera"].id,
        disease_id=core_test_data["dr"].id,
        area_id=core_test_data["area"].id,
    )
    client = auth_client(user)

    response = client.get(f"/api/encounter-viewer/images/{image.uuid}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["resource_kind"] == "image"
    assert payload["source_kind"] == "direct_image_upload"
    assert payload["images"][0]["uuid"] == image.uuid
    assert payload["images"][0]["media_url"] == f"/media/img/{image.uuid}"
