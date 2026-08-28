from __future__ import annotations

import ast
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
        "mydriatic_state": "clinical image metadata",
        "eye_side": "clinical image metadata",
        "laterality": "clinical image metadata",
        "image_quality": "clinical image assessment",
        "diagnosis": "clinical outcome",
        "grading_status": "grading workflow state",
        "workflow_state": "application workflow state",
        "encounter_status": "encounter workflow state",
        "upload_type": "upload content classification",
        "file_type": "upload content classification",
        "mime_type": "upload content classification",
        "disease_name": "clinical taxonomy",
        "camera_model": "capture-device taxonomy",
        "area_name": "clinical-area taxonomy",
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


def test_authz_core_has_no_application_domain_imports():
    """The policy engine must remain executable without importing app models."""
    violations: dict[str, list[str]] = {}
    for path in (AUTHZ_ROOT / "core").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.append(node.module)
        external = [
            name
            for name in imported
            if not name.startswith("authz_v2.")
            and name.split(".", 1)[0]
            not in {
                "__future__",
                "collections",
                "dataclasses",
                "datetime",
                "enum",
                "typing",
            }
        ]
        if external:
            violations[str(path)] = external
    assert violations == {}


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
