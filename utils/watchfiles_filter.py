from __future__ import annotations

from pathlib import Path

_IGNORED_PREFIXES = (
    "/app/files/",
    "/app/logs/",
    "/app/docs/",
    "/app/.git/",
    "/app/.venv/",
    "/app/.pytest_cache/",
    "/app/.cache/",
    "/app/.vscode/",
    "/app/.kilocode/",
    "/app/.claude/",
    "/app/.beads/",
    "/app/.github/",
)


def py_html_filter(change, path: str) -> bool:
    """Watch only Python and HTML template changes, excluding noisy paths."""
    normalized = Path(path).as_posix()
    for prefix in _IGNORED_PREFIXES:
        if normalized.startswith(prefix):
            return False
    return normalized.endswith(".py") or normalized.endswith(".html")
