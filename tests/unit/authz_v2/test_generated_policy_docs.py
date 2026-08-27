from __future__ import annotations

import csv
from pathlib import Path

from authz_v2.domain.descriptions import describe_catalogue
from authz_v2.serialization.catalogue import (
    catalogue_html,
    catalogue_markdown,
    role_action_matrix,
)

OUTPUT = Path("docs/policy/generated")


def test_generated_policy_artifacts_match_executable_catalogue_exactly():
    catalogue = describe_catalogue()
    assert (OUTPUT / "authorization_v2_foundation.md").read_text(
        encoding="utf-8"
    ) == catalogue_markdown(catalogue)
    assert (OUTPUT / "authorization_v2_foundation.html").read_text(
        encoding="utf-8"
    ) == catalogue_html(catalogue) + "\n"
    with (OUTPUT / "authorization_v2_role_action_matrix.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        assert tuple(tuple(row) for row in csv.reader(handle)) == role_action_matrix(
            catalogue
        )


def test_generated_docs_cannot_be_mistaken_for_live_enforcement():
    markdown = (OUTPUT / "authorization_v2_foundation.md").read_text(encoding="utf-8")
    assert "not registered in the live application" in markdown
    assert "128" not in markdown.splitlines()[0]
