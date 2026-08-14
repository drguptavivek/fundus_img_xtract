from pathlib import Path

from werkzeug.datastructures import MultiDict

from models import Grade
from review.task_review import _collect_changed_ai_feedback, _has_changed_ai_assessment


def _ai_grade(**overrides):
    values = {
        "id": 901,
        "task_id": 101,
        "grader_user_id": 1,
        "role_slot": "ai",
        "disease_grading_id": 1,
        "ai_review_status": "ok",
        "ai_review_comment": "Existing assessment",
    }
    values.update(overrides)
    return Grade(**values)


def test_prefilled_ai_feedback_is_not_treated_as_a_change():
    grade = _ai_grade()
    form = MultiDict(
        {
            "ai_review_status_901": "ok",
            "ai_review_comment_901": " Existing assessment ",
        }
    )

    changed, invalid = _collect_changed_ai_feedback([grade], form)

    assert invalid is False
    assert changed == []


def test_explicit_empty_fields_clear_existing_ai_feedback():
    grade = _ai_grade()
    form = MultiDict(
        {
            "ai_review_status_901": "",
            "ai_review_comment_901": "",
        }
    )

    changed, invalid = _collect_changed_ai_feedback([grade], form)

    assert invalid is False
    assert len(changed) == 1
    assert changed[0]["status"] is None
    assert changed[0]["comment"] is None


def test_omitted_ai_fields_do_not_clear_feedback():
    grade = _ai_grade()

    changed, invalid = _collect_changed_ai_feedback([grade], MultiDict({"grading_id": "1"}))

    assert invalid is False
    assert changed == []


def test_invalid_changed_status_is_rejected():
    grade = _ai_grade()
    form = MultiDict(
        {
            "ai_review_status_901": "not_valid",
            "ai_review_comment_901": "Existing assessment",
        }
    )

    changed, invalid = _collect_changed_ai_feedback([grade], form)

    assert invalid is True
    assert changed == []


def test_ai_assessment_requires_allowed_changed_nonempty_status():
    grade = _ai_grade()

    assert _has_changed_ai_assessment(
        [grade], MultiDict({"ai_review_status_901": "minor_miss"})
    ) is True
    assert _has_changed_ai_assessment(
        [grade], MultiDict({"ai_review_status_901": "ok"})
    ) is False
    assert _has_changed_ai_assessment(
        [grade], MultiDict({"ai_review_status_901": "", "ai_review_comment_901": "Text only"})
    ) is False
    assert _has_changed_ai_assessment(
        [grade], MultiDict({"ai_review_status_901": "invalid"})
    ) is False


def test_review_template_requires_explicit_human_grade_selection():
    template = Path("templates/review/task_detail_review.html").read_text(encoding="utf-8")
    script = Path("static/js/review-task-detail.js").read_text(encoding="utf-8")

    assert "existing_review_grade.disease_grading_id==grade.id %}checked" not in template
    assert "matchingExisting.checked = true" not in script
    assert "const shouldShow = hasSelection;" in script
    assert ">Updated based on AI result</label>" in template
    assert ">Updated NOT based on AI result</label>" in template
    assert 'name="review_grade_updated_at"' in template
    assert 'name="consensus_decided_at"' in template
    assert 'name="ai_reviewed_at_{{ ai_grade.id }}"' in template
    assert template.count("data-review-write-action") == 2
    assert 'data-next-task-available="{{ \'1\' if next_task_id else \'0\' }}" disabled' in template
    assert "const hasAiFeedbackWrite = hasChangedAiAssessment();" in script
    assert "const hasWrite = (hasHumanGrade || hasAiFeedbackWrite) && humanSelectionComplete;" in script
    assert "button.disabled = !hasWrite || (needsNextTask && !saveNextAvailable);" in script
    assert "cancelNextButton.disabled = !cancelNextAvailable;" in script
    assert "updateReviewSubmissionState();" in script
    assert "change a Quality Assessment selection. A comment alone is not sufficient." in template
    assert 'href="{{ cancel_close_url }}"' in template
    assert "Cancel &amp; Close" in template
    assert "-review-submit-v2" in template


def test_review_navigation_does_not_trust_submitted_next_task_id():
    route = Path("review/task_review.py").read_text(encoding="utf-8")

    assert 'target_next_task_id = nav_result.get("next_task_id")' in route
    assert "target_next_task_id = form_next_task_id or next_task_id" not in route


def test_discrepancy_review_ui_exposes_status_cohorts_and_csv_queue():
    template = Path("templates/review/discrepancy_review.html").read_text(encoding="utf-8")

    for value in ("unreviewed", "human", "ai", "both", "any"):
        assert f'<option value="{value}"' in template
    assert 'id="projectSelect"' in template
    assert 'name="project_id"' in template
    assert "fundus_api.discrepancy_review_filter_options" in template
    review_status_position = template.index('id="hasHumanReviewSelect"')
    ai_review_status_position = template.index('id="aiReviewStatusDropdown"')
    assert template.rfind('<div class="row g-3 mt-2 disease-dependent"', 0, review_status_position) > template.index(
        'id="aiGradeDropdown"'
    )
    assert review_status_position < ai_review_status_position
    assert 'data-bs-target="#reviewQueueUploadModal"' in template
    assert 'id="reviewQueueUploadModal"' in template
    assert 'id="reviewQueueUploadForm"' in template
    assert template.index('id="reviewQueueUploadModal"') < template.index(
        'id="reviewQueueUploadForm"'
    )
    assert '{{ csrf_field() }}' in template
    assert 'name="review_queue"' in template
    assert "fundus_api.create_discrepancy_review_queue" in template
