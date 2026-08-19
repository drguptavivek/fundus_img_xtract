from __future__ import annotations

from types import SimpleNamespace

from remote_inference.dr_dme_service import evaluate_encounter, has_completed_dr_ocr, normalize_eye, normalize_focus


def image(image_id, *, eye="OD", focus="MACULA", filename="image.jpg"):
    return SimpleNamespace(
        id=image_id,
        uuid=f"image-{image_id}",
        spatial_position=image_id,
        asset_kind="clinical_image",
        creates_task=True,
        is_not_gradable=False,
        original_filename=filename,
        edited_filename=None,
        metadata_json={"laterality": eye, "focus": focus},
    )


def encounter(
    images,
    *,
    verified="verified",
    patient_id="UHID-1",
    age=55,
    sex="female",
    is_monocular=False,
    attachments=(),
):
    return SimpleNamespace(
        encounter_verified_status=verified,
        patient_id=patient_id,
        metadata_json={
            "patient": {
                "patient_age_yrs": age,
                "sex": sex,
                "is_monocular": is_monocular,
            }
        },
        encounter_set_images=list(images),
        encounter_set_attachments=list(attachments),
    )


def test_normalization_is_strict_for_laterality_and_focus():
    assert [normalize_eye(value) for value in ("OD", "R", "right", "right eye")] == ["right"] * 4
    assert [normalize_eye(value) for value in ("OS", "L", "left", "left eye")] == ["left"] * 4
    assert normalize_eye("OU") is None
    assert normalize_focus("MACULA") == "macula"
    assert normalize_focus("DISC") == "disc"


def test_candidate_selects_only_macula_with_unambiguous_eye():
    result = evaluate_encounter(
        encounter([image(1), image(2, eye="OS"), image(3, focus="DISC"), image(4, eye="OU")]),
        require_verified=True,
    )

    assert result.eligible is True
    assert [row.image_id for row in result.images] == [1, 2]
    assert result.eye_counts == {"right": 1, "left": 1}


def test_candidate_never_truncates_more_than_ten_images_per_eye():
    result = evaluate_encounter(encounter([image(index) for index in range(1, 12)]))

    assert result.eligible is False
    assert len(result.images) == 11
    assert "More than 10 right-eye images" in result.issues[-1]


def test_manual_candidate_requires_verification_and_patient_contract():
    result = evaluate_encounter(
        encounter(
            [image(1), image(2, eye="OS")],
            verified="pending",
            patient_id="x" * 31,
            age=121,
            sex="unknown",
        ),
        require_verified=True,
    )

    assert result.eligible is False
    assert len(result.issues) == 4


def test_candidate_requires_both_eyes_unless_canonical_monocular_flag_is_true():
    binocular = evaluate_encounter(encounter([image(1)]))
    monocular = evaluate_encounter(encounter([image(1)], is_monocular=True))

    assert binocular.eligible is False
    assert "Both eyes require a macula image unless the patient is marked monocular." in binocular.issues
    assert monocular.eligible is True
    assert binocular.is_monocular is False
    assert monocular.is_monocular is True


def test_candidate_requires_canonical_age_and_sex():
    valid = evaluate_encounter(encounter([image(1), image(2, eye="OS")], age="55", sex="male"))
    missing_age = evaluate_encounter(encounter([image(1), image(2, eye="OS")], age=None))
    missing_sex = evaluate_encounter(encounter([image(1), image(2, eye="OS")], sex=None))

    assert valid.eligible is True
    assert "Patient age must be between 0 and 120." in missing_age.issues
    assert "Patient sex must be male, female, or other." in missing_sex.issues


def test_ocr_eligibility_requires_completed_normalized_dr_report():
    upstream_only = SimpleNamespace(metadata_json={"ocr": {"status": "completed"}, "report_type": "DR"})
    local = SimpleNamespace(metadata_json={"ocr": {"status": "completed", "dr_report": {"result": "positive"}}})

    assert has_completed_dr_ocr(encounter([image(1)], attachments=[upstream_only])) is False
    assert has_completed_dr_ocr(encounter([image(1)], attachments=[local])) is True
