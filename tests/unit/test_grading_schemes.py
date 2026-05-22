from uuid import uuid4

from grading_schemes.service import (
    GradeFeatureInput,
    GradeInput,
    GradingSchemeInput,
    create_grade,
    create_grading_scheme,
    get_grading_scheme,
    list_grading_schemes,
    update_grade,
    update_grading_scheme,
)
from models import Disease, DiseaseGrading, GradingsFeatures, LinkedDiseaseGrading


def test_create_and_list_grading_scheme_uses_disease_as_scheme(app, db_session):
    suffix = uuid4().hex[:8]
    result = create_grading_scheme(
        GradingSchemeInput(name=f"Test Image Scheme {suffix}", grading_scope="image")
    )

    assert result.success is True
    scheme_id = result.payload["grading_scheme_id"]
    disease = db_session.get(Disease, scheme_id)
    assert disease.name == f"Test Image Scheme {suffix}"
    assert disease.grading_scope == "image"

    rows = list_grading_schemes()
    created = next(row for row in rows if row["id"] == scheme_id)
    assert created["name"] == f"Test Image Scheme {suffix}"
    assert created["grade_count"] == 0
    assert created["feature_count"] == 0


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

    update_result = update_grade(
        disease.id,
        grade_id,
        GradeInput(
            impression="Mild",
            display_order=2,
            is_active=False,
            prioritize_for_task_selection=False,
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
    assert [feature["label"] for feature in updated["features"]] == ["Feature B"]
