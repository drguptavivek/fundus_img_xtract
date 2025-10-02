"""Admin log viewer routes."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from flask import current_app, render_template, request

from auth.roles import roles_required


def _resolve_log_root() -> Path:
    """Return the base directory that contains readable log files."""
    configured = current_app.config.get("LOG_VIEWER_ROOT")
    if configured:
        log_root = Path(configured)
    else:
        log_root = Path(current_app.root_path) / "logs"
    return log_root.resolve()


def _iter_log_files(log_root: Path) -> Iterable[Path]:
    """Yield candidate log files inside the log root (non-recursive)."""
    if not log_root.exists() or not log_root.is_dir():
        return []
    return sorted(
        (p for p in log_root.iterdir() if p.is_file() and p.suffix in {".log", ".txt"}),
        key=lambda p: p.name.lower(),
    )


def _safe_log_path(log_root: Path, filename: str) -> Path | None:
    """Return a safe path for the requested filename or None if invalid."""
    if not filename:
        return None
    candidate = (log_root / filename).resolve()
    try:
        candidate.relative_to(log_root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _read_log_tail(path: Path, max_bytes: int) -> tuple[str, bool]:
    """Read up to ``max_bytes`` from the end of ``path``; return text and truncation flag."""
    try:
        file_size = path.stat().st_size
    except OSError:
        return "Failed to read log file metadata.", False

    truncated = False
    start = 0
    if file_size > max_bytes:
        truncated = True
        start = file_size - max_bytes
    try:
        with path.open("rb") as fh:
            fh.seek(start, os.SEEK_SET)
            data = fh.read()
    except OSError:
        return "Failed to read log file contents.", False

    text = data.decode("utf-8", errors="replace")
    return text, truncated


@roles_required("admin")
def log_viewer():
    """Render the admin log viewer with selectable log files."""
    log_root = _resolve_log_root()
    log_files = list(_iter_log_files(log_root))

    selected_name = request.args.get("file")
    selected_path = _safe_log_path(log_root, selected_name) if selected_name else None

    if not selected_path and log_files:
        selected_path = log_files[0]
        selected_name = selected_path.name

    log_content = ""
    content_truncated = False
    selected_meta: dict[str, object] | None = None

    if selected_path:
        max_bytes = int(current_app.config.get("LOG_VIEWER_MAX_BYTES", 500_000))
        log_content, content_truncated = _read_log_tail(selected_path, max_bytes)
        try:
            stat = selected_path.stat()
            selected_meta = {
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            }
        except OSError:
            selected_meta = None

    log_file_entries: list[dict[str, object]] = []
    for path in log_files:
        size = None
        modified_at = None
        try:
            stat = path.stat()
            size = stat.st_size
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        except OSError:
            pass
        log_file_entries.append(
            {
                "name": path.name,
                "size_bytes": size,
                "modified_at": modified_at,
            }
        )

    context = {
        "log_files": log_file_entries,
        "selected_file": selected_name,
        "log_content": log_content,
        "content_truncated": content_truncated,
        "selected_meta": selected_meta,
        "log_root": str(log_root),
    }

    return render_template("admin/log_viewer.html", **context)
