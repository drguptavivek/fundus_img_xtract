"""Emit a deterministic baseline of live HTTP and Celery authorization consumers."""

from __future__ import annotations

import ast
import inspect
import json
import re
import sys
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from authz_v2.core.actions import ACTION_MANIFEST, ACTION_MIGRATION_MAP
from authz_v2.flask.manifest import build_route_manifest

_ACTION_NAMES = frozenset(ACTION_MIGRATION_MAP) | ACTION_MANIFEST
_ACTION_PATTERN = re.compile(
    r"(?P<quote>['\"])(?P<action>"
    + "|".join(re.escape(name) for name in sorted(_ACTION_NAMES, key=len, reverse=True))
    + r")(?P=quote)"
)
_LIST_MATERIALIZERS = frozenset({"all", "paginate", "yield_per"})
_EXCLUDED_QUERY_PARTS = frozenset({".git", ".venv", "migrations", "tests"})


@dataclass(frozen=True)
class ConsumerInventoryRow:
    kind: str
    name: str
    methods: tuple[str, ...]
    path: str | None
    source: str | None
    line: int | None
    canonical_actions: tuple[str, ...]
    classification: str


def _source_details(value) -> tuple[str | None, int | None, str]:
    try:
        original = inspect.unwrap(value)
        source_file = inspect.getsourcefile(original)
        lines, line = inspect.getsourcelines(original)
    except (OSError, TypeError):
        return None, None, ""
    if source_file is None:
        return None, line, "".join(lines)
    root = Path(__file__).resolve().parents[1]
    path = Path(source_file).resolve()
    try:
        display = str(path.relative_to(root))
    except ValueError:
        display = str(path)
    return display, line, "".join(lines)


def _actions(source: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                ACTION_MIGRATION_MAP.get(match.group("action"), match.group("action"))
                for match in _ACTION_PATTERN.finditer(source)
            }
        )
    )


def _query_candidates(root: Path) -> tuple[ConsumerInventoryRow, ...]:
    rows = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(part in _EXCLUDED_QUERY_PARTS for part in relative.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(relative))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _LIST_MATERIALIZERS
            ):
                continue
            line = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            rows.append(
                ConsumerInventoryRow(
                    "query",
                    f"{relative}:{node.lineno}:{node.col_offset}",
                    (),
                    node.func.attr,
                    str(relative),
                    node.lineno,
                    _actions(line),
                    "query_candidate_unmapped",
                )
            )
    return tuple(rows)


def build_live_consumer_inventory(app, celery_app) -> tuple[ConsumerInventoryRow, ...]:
    """Enumerate every runtime route/task and explicitly expose migration gaps."""
    route_metadata = {row.endpoint: row for row in build_route_manifest(app)}
    rows: list[ConsumerInventoryRow] = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        view = app.view_functions.get(rule.endpoint)
        source, line, body = _source_details(view)
        if source and source.startswith("tests/"):
            continue
        metadata = route_metadata[rule.endpoint]
        actions = (metadata.action,) if metadata.action else _actions(body)
        classification = (
            "authz_v2"
            if metadata.action
            else "legacy_action_literal"
            if actions
            else "legacy_unmapped"
        )
        rows.append(
            ConsumerInventoryRow(
                "http",
                rule.endpoint,
                tuple(sorted(set(rule.methods or ()) - {"HEAD", "OPTIONS"})),
                str(rule),
                source,
                line,
                actions,
                classification,
            )
        )
    for name, task in celery_app.tasks.items():
        if not name.startswith("celery_tasks."):
            continue
        source, line, body = _source_details(task.run)
        actions = _actions(body)
        rows.append(
            ConsumerInventoryRow(
                "celery",
                name,
                (),
                None,
                source,
                line,
                actions,
                "authz_action_literal" if actions else "automation_unmapped",
            )
        )
    rows.extend(_query_candidates(Path(__file__).resolve().parents[1]))
    return tuple(
        sorted(rows, key=lambda row: (row.kind, row.name, row.path or "", row.methods))
    )


def inventory_fingerprint(rows: tuple[ConsumerInventoryRow, ...]) -> str:
    """Hash runtime identities so route/task drift must be reviewed explicitly."""
    payload = [
        (row.kind, row.name, row.methods, row.path, row.source, row.line)
        for row in rows
    ]
    return sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=False).encode("utf-8")
    ).hexdigest()


def main() -> None:
    from app import create_app
    from celery_app import celery_app
    from celery_tasks.tasks import _import_all

    with redirect_stdout(sys.stderr):
        app = create_app()
        _import_all()
    rows = build_live_consumer_inventory(app, celery_app)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.classification] = counts.get(row.classification, 0) + 1
    print(
        json.dumps(
            {
                "schema_version": 1,
                "identity_fingerprint": inventory_fingerprint(rows),
                "counts": dict(sorted(counts.items())),
                "consumers": [asdict(row) for row in rows],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
