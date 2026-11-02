import pytest

from project_review.export_artifacts import export_scope_allowed, record_export_scope


@pytest.mark.parametrize("change", ["grant", "labs", "pii", "user", "project", "missing", "malformed"])
def test_saved_artifacts_reject_changed_authority(tmp_path, change):
    export_dir = tmp_path / "job-token"
    export_dir.mkdir()
    scope = dict(project_id=1, user_id=2, lab_unit_ids={3, 4}, pii_lab_unit_ids={3}, grant_uuid="grant-a")
    record_export_scope(export_dir, **scope)
    assert export_scope_allowed(export_dir, **scope)
    current = dict(scope)
    if change == "grant": current["grant_uuid"] = "grant-b"
    if change == "labs": current["lab_unit_ids"] = {3}
    if change == "pii": current["pii_lab_unit_ids"] = set()
    if change == "user": current["user_id"] = 9
    if change == "project": current["project_id"] = 9
    if change == "missing": (tmp_path / "job-token.authorization.json").unlink()
    if change == "malformed": (tmp_path / "job-token.authorization.json").write_text("[]")
    assert not export_scope_allowed(export_dir, **current)
    assert not list(export_dir.iterdir())
