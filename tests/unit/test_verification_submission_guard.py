from pathlib import Path

import pytest


def test_shared_submission_guard_blocks_reentry_and_restores_controls():
    script = Path("static/js/submission-guard.js").read_text(encoding="utf-8")

    assert "const activeSubmissions = new WeakMap();" in script
    assert "if (!target || activeSubmissions.has(target)) return null;" in script
    assert "event.preventDefault();" in script
    assert "activeSubmissions.delete(target);" in script
    assert "snapshot.control.disabled = snapshot.disabled;" in script
    assert "function release(target)" in script
    assert "global.SubmissionGuard = Object.freeze({acquire, isActive, release});" in script


def test_encounter_set_verification_uses_shared_guard_for_mutations():
    template = Path(
        "verify_encounter_set/templates/verify_encounter_set/verify.html"
    ).read_text(encoding="utf-8")
    routes = Path("verify_encounter_set/routes.py").read_text(encoding="utf-8")

    assert "filename='js/submission-guard.js'" in template
    assert "window.SubmissionGuard.acquire(shell" in template
    assert "data-verification-submit-overlay" in template
    assert "Saving verification and loading the next EncounterSet…" in template
    assert "if (!submission) return;" in template
    assert "if (!navigating) submission.release();" in template
    assert ".with_for_update()" in routes


def test_grading_workbench_reuses_shared_submission_guard():
    template = Path("templates/grading/workbench.html").read_text(encoding="utf-8")

    assert "filename='js/submission-guard.js'" in template
    assert "window.SubmissionGuard.acquire(workbenchForm" in template
    assert "submission.release();" in template
    assert template.index("filename='js/submission-guard.js'") < template.index(
        "window.SubmissionGuard.acquire(workbenchForm"
    )


@pytest.mark.parametrize(
    ("template_path", "script_path"),
    [
        ("templates/verify_remedio/edit.html", "static/js/verify_remedio_edit.js"),
        ("templates/verify_remedio_dr/edit.html", "static/js/dr_edit.js"),
        ("templates/verify_remedio_glaucoma/edit.html", "static/js/glaucoma_edit.js"),
        ("templates/verify_remedio_nodr/edit.html", "static/js/dr_edit.js"),
    ],
)
def test_remidio_verifiers_reuse_shared_submission_guard(template_path, script_path):
    template = Path(template_path).read_text(encoding="utf-8")
    script = Path(script_path).read_text(encoding="utf-8")

    assert "data-submission-guard" in template
    assert "filename='js/submission-guard.js'" in template
    assert "window.SubmissionGuard.acquire" in script
    assert ".finally(" in script
    assert template.index("filename='js/submission-guard.js'") < template.index(
        f"filename='js/{Path(script_path).name}'"
    )
