"""Generate reviewable policy artifacts from the executable foundation."""

from __future__ import annotations

import csv
from pathlib import Path

from authz_v2.domain.descriptions import describe_catalogue
from authz_v2.serialization.catalogue import (
    catalogue_html,
    catalogue_markdown,
    role_action_matrix,
)


def generate(output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    catalogue = describe_catalogue()
    markdown_path = output_dir / "authorization_v2_foundation.md"
    html_path = output_dir / "authorization_v2_foundation.html"
    matrix_path = output_dir / "authorization_v2_role_action_matrix.csv"
    markdown_path.write_text(catalogue_markdown(catalogue), encoding="utf-8")
    html_path.write_text(catalogue_html(catalogue) + "\n", encoding="utf-8")
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(role_action_matrix(catalogue))
    return markdown_path, html_path, matrix_path


if __name__ == "__main__":
    generate(Path("docs/policy/generated"))
