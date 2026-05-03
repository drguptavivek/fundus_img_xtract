from pathlib import Path

import pytest

from authz.registry import ActionRegistryError, get_action, load_action_registry


REQUIRED_DOMAIN_FILES = {
    "account.toml",
    "ad_hoc_tasks.toml",
    "admin.toml",
    "analytics.toml",
    "api.toml",
    "auth.toml",
    "datasets.toml",
    "discrepancy_review.toml",
    "docs.toml",
    "glaucoma_ai.toml",
    "grading.toml",
    "help.toml",
    "intra_rater.toml",
    "jobs.toml",
    "media.toml",
    "notifications.toml",
    "preprocess.toml",
    "public.toml",
    "reports.toml",
    "screenings.toml",
    "search.toml",
    "tasks.toml",
    "upload.toml",
    "verification.toml",
}


def test_registry_has_toml_file_for_each_route_domain() -> None:
    registry_dir = Path("authz/actions")
    actual_files = {path.name for path in registry_dir.glob("*.toml")}

    assert REQUIRED_DOMAIN_FILES.issubset(actual_files)


def test_loads_actions_from_per_domain_toml_files() -> None:
    registry = load_action_registry()

    upload_action = registry["upload.direct.create"]
    grading_action = registry["grading.resident.submit"]

    assert upload_action.domain == "upload"
    assert upload_action.zone == "api"
    assert upload_action.resource_type == "upload_selection"
    assert upload_action.requires_resource is True
    assert grading_action.domain == "grading"
    assert grading_action.resource_type == "grading_task"
    assert "analytics.encounters.view" in registry
    assert registry["verification.direct.update"].resource_type == "direct_image_upload"
    assert registry["verification.remidio.update"].resource_type == "encounter"
    assert registry["verification.pregraded.update"].resource_type == "direct_image_upload"
    assert registry["dataset.export.create"].domain == "datasets"
    assert registry["review.discrepancy.view"].domain == "discrepancy_review"
    assert registry["intra_rater.batch.create"].domain == "intra_rater"
    assert registry["ad_hoc_task.create"].domain == "ad_hoc_tasks"
    assert registry["admin.users.view"].domain == "admin"


def test_get_action_rejects_unknown_actions() -> None:
    with pytest.raises(ActionRegistryError, match="Unknown authz action"):
        get_action("missing.action")


def test_rejects_duplicate_actions_across_toml_files(tmp_path: Path) -> None:
    first = tmp_path / "upload.toml"
    second = tmp_path / "admin.toml"
    first.write_text(
        """
[[actions]]
name = "upload.direct.create"
domain = "upload"
zone = "api"
description = "Create direct upload"
resource_type = "upload_selection"
requires_resource = true
""".strip(),
        encoding="utf-8",
    )
    second.write_text(
        """
[[actions]]
name = "upload.direct.create"
domain = "admin"
zone = "web"
description = "Duplicate action"
resource_type = "upload_selection"
requires_resource = true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ActionRegistryError, match="Duplicate authz action"):
        load_action_registry(tmp_path)


def test_rejects_policy_actions_missing_from_registry(tmp_path: Path) -> None:
    registry_file = tmp_path / "upload.toml"
    registry_file.write_text(
        """
[[actions]]
name = "upload.direct.create"
domain = "upload"
zone = "api"
description = "Create direct upload"
resource_type = "upload_selection"
requires_resource = true
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ActionRegistryError, match="Policy action is not registered"):
        load_action_registry(tmp_path)
