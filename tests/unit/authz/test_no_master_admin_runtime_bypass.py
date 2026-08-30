"""Guard the active Admin role as the only runtime Admin credential."""

from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EXCLUDED_PARTS = frozenset({".git", ".serena", ".venv", "migrations", "tests"})


def test_production_code_never_reads_legacy_is_master_admin_field():
    """The dormant database flag must never become an authorization bypass."""
    reads: list[str] = []

    for path in REPOSITORY_ROOT.rglob("*.py"):
        relative = path.relative_to(REPOSITORY_ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "is_master_admin"
                and isinstance(node.ctx, ast.Load)
            ):
                reads.append(f"{relative}:{node.lineno}")

    assert reads == [], (
        "Runtime authorization must derive Admin status from the active 'admin' role; "
        f"legacy is_master_admin reads found at {reads}"
    )
