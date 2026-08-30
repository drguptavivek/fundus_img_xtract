from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_unqualified_profile_assignment_has_visible_warning_and_confirmation():
    template = (
        PROJECT_ROOT / "templates/admin/partials/project_uploader_assignments.html"
    ).read_text()
    javascript = (PROJECT_ROOT / "static/js/admin-upload-profiles.js").read_text()

    assert "data-uploader-qualified" in template
    assert "data-uploader-role-warning" in template
    assert "data-uploader-role-grant-link" in template
    assert "Open role editor" in template
    assert "Ask a System Admin or User Manager" in template
    assert "requires_file_uploader" in template
    assert "requires_pregraded_uploader" in template
    assert "syncUploaderRoleWarning" in javascript
    assert "window.confirm" in javascript
    assert "uploading will remain blocked" in javascript
