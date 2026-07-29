from uuid import uuid4

from grading_schemes.service import (
    GradeFeatureInput,
    GradeInput,
    GradingSchemeInput,
    create_grade,
    create_grading_scheme,
    duplicate_grading_scheme,
    get_grading_scheme,
    list_grading_schemes,
    update_grade,
    update_grading_scheme,
)
from models import Disease, DiseaseGrading, GradingsFeatures, LinkedDiseaseGrading


def test_create_and_list_grading_scheme_uses_disease_as_scheme(app, db_session):
    suffix = uuid4().hex[:8]
    result = create_grading_scheme(
        GradingSchemeInput(name=f"Test Image Scheme {suffix}", grading_scope="image", remidio_ocr_linkage="dr")
    )

    assert result.success is True
    scheme_id = result.payload["grading_scheme_id"]
    disease = db_session.get(Disease, scheme_id)
    assert disease.name == f"Test Image Scheme {suffix}"
    assert disease.grading_scope == "image"
    assert disease.remidio_ocr_linkage == "dr"

    rows = list_grading_schemes()
    created = next(row for row in rows if row["id"] == scheme_id)
    assert created["name"] == f"Test Image Scheme {suffix}"
    assert created["remidio_ocr_linkage"] == "dr"
    assert created["grade_count"] == 0
    assert created["feature_count"] == 0


def test_image_grading_scheme_accepts_amd_remidio_ocr_linkage(app, db_session):
    suffix = uuid4().hex[:8]
    result = create_grading_scheme(
        GradingSchemeInput(name=f"AMD OCR Scheme {suffix}", grading_scope="image", remidio_ocr_linkage="amd")
    )

    assert result.success is True
    disease = db_session.get(Disease, result.payload["grading_scheme_id"])
    assert disease.remidio_ocr_linkage == "amd"


def test_encounter_grading_scheme_normalizes_remidio_ocr_linkage(app, db_session):
    suffix = uuid4().hex[:8]
    result = create_grading_scheme(
        GradingSchemeInput(name=f"Encounter OCR Scheme {suffix}", grading_scope="encounter", remidio_ocr_linkage="glaucoma")
    )

    assert result.success is True
    scheme_id = result.payload["grading_scheme_id"]
    disease = db_session.get(Disease, scheme_id)
    assert disease.grading_scope == "encounter"
    assert disease.remidio_ocr_linkage == "none"


def test_grading_scheme_detail_counts_grades_and_features(app, db_session):
    suffix = uuid4().hex[:8]
    disease = Disease(name=f"Encounter Scheme {suffix}", grading_scope="encounter")
    db_session.add(disease)
    db_session.flush()
    grade = DiseaseGrading(disease_id=disease.id, impression="Normal", display_order=1, is_active=True)
    db_session.add(grade)
    db_session.flush()
    db_session.add(GradingsFeatures(disease_grading_id=grade.id, sr_no=1, label="No abnormality"))
    db_session.flush()

    result = get_grading_scheme(disease.id)

    assert result.success is True
    payload = result.payload["grading_scheme"]
    assert payload["grading_scope"] == "encounter"
    assert payload["grade_count"] == 1
    assert payload["feature_count"] == 1
    assert payload["grades"][0]["prioritize_for_task_selection"] is False
    assert payload["grades"][0]["is_ungradable"] is False
    assert payload["grades"][0]["features"][0]["label"] == "No abnormality"


def test_grading_scheme_list_shows_linked_parent_and_children(app, db_session):
    suffix = uuid4().hex[:8]
    parent = Disease(name=f"Parent Scheme {suffix}", grading_scope="image")
    child = Disease(name=f"Child Scheme {suffix}", grading_scope="image")
    db_session.add_all([parent, child])
    db_session.flush()
    db_session.add(
        LinkedDiseaseGrading(
            primary_disease_id=parent.id,
            linked_disease_id=child.id,
            display_order=1,
            is_active=True,
        )
    )
    db_session.flush()

    rows = list_grading_schemes()
    parent_row = next(row for row in rows if row["id"] == parent.id)
    child_row = next(row for row in rows if row["id"] == child.id)

    assert parent_row["linked_child_count"] == 1
    assert parent_row["linkage"]["children"][0]["name"] == child.name
    assert child_row["is_linked_child"] is True
    assert child_row["linkage"]["parent"]["name"] == parent.name


def test_update_grading_scheme_validates_scope(app, db_session):
    suffix = uuid4().hex[:8]
    disease = Disease(name=f"Scope Scheme {suffix}", grading_scope="image")
    db_session.add(disease)
    db_session.flush()

    result = update_grading_scheme(
        disease.id,
        GradingSchemeInput(name=disease.name, grading_scope="invalid"),
    )

    assert result.success is False
    assert result.status_code == 400


def test_create_and_update_grade_replaces_features(app, db_session):
    suffix = uuid4().hex[:8]
    disease = Disease(name=f"Grade Scheme {suffix}", grading_scope="image")
    db_session.add(disease)
    db_session.flush()

    create_result = create_grade(
        disease.id,
        GradeInput(
            impression="Mild",
            display_order=1,
            is_active=True,
            prioritize_for_task_selection=True,
            is_ungradable=True,
            guidelines="Initial guideline",
            features=[GradeFeatureInput(sr_no=1, label="Feature A")],
        ),
    )

    assert create_result.success is True
    grade_id = create_result.payload["grade_id"]
    db_session.expire_all()
    detail = get_grading_scheme(disease.id).payload["grading_scheme"]
    assert detail["grades"][0]["features"][0]["label"] == "Feature A"
    assert detail["grades"][0]["prioritize_for_task_selection"] is True
    assert detail["grades"][0]["is_ungradable"] is True

    update_result = update_grade(
        disease.id,
        grade_id,
        GradeInput(
            impression="Mild",
            display_order=2,
            is_active=False,
            prioritize_for_task_selection=False,
            is_ungradable=False,
            guidelines=None,
            features=[GradeFeatureInput(sr_no=1, label="Feature B")],
        ),
    )

    assert update_result.success is True
    db_session.expire_all()
    updated = get_grading_scheme(disease.id).payload["grading_scheme"]["grades"][0]
    assert updated["display_order"] == 2
    assert updated["is_active"] is False
    assert updated["prioritize_for_task_selection"] is False
    assert updated["is_ungradable"] is False
    assert [feature["label"] for feature in updated["features"]] == ["Feature B"]


def test_duplicate_grading_scheme_copies_grades_features_and_uses_unique_name(app, db_session):
    suffix = uuid4().hex[:8]
    disease = Disease(name=f"Duplicate Source {suffix}", grading_scope="image", remidio_ocr_linkage="glaucoma")
    db_session.add(disease)
    db_session.flush()
    grade = DiseaseGrading(
        disease_id=disease.id,
        impression="Referable",
        display_order=2,
        is_active=False,
        prioritize_for_task_selection=True,
        is_ungradable=True,
        guidelines="<strong>Review urgently</strong><script>alert(1)</script>",
    )
    db_session.add(grade)
    db_session.flush()
    db_session.add(GradingsFeatures(disease_grading_id=grade.id, sr_no=3, label="Disc pallor"))
    db_session.flush()

    first = duplicate_grading_scheme(disease.id)
    second = duplicate_grading_scheme(disease.id)

    assert first.success is True
    assert first.status_code == 201
    assert first.payload["grading_scheme_name"] == f"Copy of Duplicate Source {suffix}"
    assert second.success is True
    assert second.payload["grading_scheme_name"] == f"Copy of Duplicate Source {suffix} (2)"

    copied = get_grading_scheme(first.payload["grading_scheme_id"]).payload["grading_scheme"]
    assert copied["name"] == f"Copy of Duplicate Source {suffix}"
    assert copied["grading_scope"] == "image"
    assert copied["remidio_ocr_linkage"] == "glaucoma"
    assert copied["usage_total"] == 0
    assert copied["grade_count"] == 1
    copied_grade = copied["grades"][0]
    assert copied_grade["impression"] == "Referable"
    assert copied_grade["display_order"] == 2
    assert copied_grade["is_active"] is False
    assert copied_grade["prioritize_for_task_selection"] is True
    assert copied_grade["is_ungradable"] is True
    assert copied_grade["guidelines"] == "<strong>Review urgently</strong>alert(1)"
    assert copied_grade["features"] == [{"id": copied_grade["features"][0]["id"], "sr_no": 3, "label": "Disc pallor"}]
