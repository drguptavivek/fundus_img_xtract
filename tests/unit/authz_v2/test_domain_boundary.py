from __future__ import annotations

from pathlib import Path


AUTHZ_ROOT = Path("authz_v2")


def test_authz_does_not_encode_application_workflow_or_content_rules():
    """Keep business eligibility in application services, not authorization."""
    forbidden = {
        "sync.status": "S3 retry lifecycle",
        "task.state": "grading workflow state",
        "dataset.is_finalized": "dataset lifecycle",
        "selection_mode": "upload field content",
        "validation_regex": "upload field content",
        "is_mydriatic": "clinical image metadata",
        "camera_id": "clinical image metadata",
        "area_id": "clinical image metadata",
    }
    python_sources = {
        path: path.read_text(encoding="utf-8")
        for path in AUTHZ_ROOT.rglob("*.py")
    }
    leaks = {
        label: str(path)
        for path, source in python_sources.items()
        for token, label in forbidden.items()
        if token in source
    }
    assert leaks == {}


def test_domain_valid_is_limited_to_authorization_state_inputs():
    """The generic fact may gate authorization state, never business outcomes."""
    allowed_modules = {
        "authz_v2/resources/adapters.py",
        "authz_v2/resources/grants.py",
        "authz_v2/resources/projects.py",
        "authz_v2/resources/relationships.py",
        "authz_v2/resources/upload_targets.py",
        "authz_v2/resources/users.py",
    }
    producers = {
        str(path)
        for path in AUTHZ_ROOT.rglob("*.py")
        if "domain_valid=" in path.read_text(encoding="utf-8")
    }
    assert producers <= allowed_modules
