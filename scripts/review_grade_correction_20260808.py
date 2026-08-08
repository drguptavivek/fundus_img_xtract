"""Auditable one-time correction for discrepancy-review attribution.

This module is intentionally versioned and called by its Alembic migration.
It imports only structured, non-PII evidence from the retained grades logs,
archives complete database snapshots, and applies only corrections that can be
proved from both the logs and the current relational state.

Run a read-only preview with::

    uv run scripts/review_grade_correction_20260808.py --dry-run

Production writes are performed by the Alembic migration, not this CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import Connection, text


MIGRATION_ID = "c8a4e2f1d9b7"
SCRIPT_NAME = "scripts/review_grade_correction_20260808.py"
CORRECTION_VERSION = 1
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"

_TIMESTAMP_RE = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
_REVIEW_RE = re.compile(
    r"Grade submission .*?\[user_id: (?P<user_id>\d+)\] "
    r"\[Task ID: (?P<task_id>\d+)\] \[Slot Type: review\] "
    r"\[Disease ID: (?P<disease_id>\d+)\] \[Grade: (?P<grade>\d+|None)\] "
    r"\[Type: (?P<event_type>new|revision)\] \[Grade ID: (?P<grade_id>\d+|N/A)\]"
)
_CONSENSUS_RE = re.compile(
    r"Consensus override via review \[user_id: (?P<user_id>\d+)\] "
    r"\[task_id: (?P<task_id>\d+)\] \[new_grade_id: (?P<new_grade_id>\d+)\] "
    r"\[prev_method: (?P<prev_method>[^\]]+)\] "
    r"\[prev_grade_id: (?P<prev_grade_id>\d+|None)\]"
)
_AI_HEADER_RE = re.compile(
    r"AI review feedback \[user_id: (?P<user_id>\d+)\] \[task_id: (?P<task_id>\d+)\] (?P<body>.+)$"
)
_AI_ITEM_RE = re.compile(
    r"AI grade (?P<grade_id>\d+) status=(?P<status>[a-z_]+|none) model=(?P<model>[^;]+)"
)
_INFLUENCE_RE = re.compile(r"(?im)^AI influence:\s*(yes|no)\s*$")
_SAFE_MATVIEW_RE = re.compile(r"^mvw_image_listing_[a-z0-9_]+_v2$")


class CorrectionInvariantError(RuntimeError):
    """Raised before mutation when evidence cannot prove a correction."""


@dataclass(frozen=True)
class ParsedLogEvidence:
    review_events_by_task: Mapping[int, tuple[dict[str, Any], ...]]
    consensus_events_by_task: Mapping[int, tuple[dict[str, Any], ...]]
    ai_events_by_grade: Mapping[int, tuple[dict[str, Any], ...]]
    source_manifest: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CorrectionPlan:
    ai_feedback_rows: tuple[dict[str, Any], ...]
    ambiguous_reviews: tuple[dict[str, Any], ...]
    tagged_reviews: tuple[dict[str, Any], ...]
    archive_payloads: tuple[dict[str, Any], ...]
    log_sources: tuple[dict[str, Any], ...]

    def summary(self) -> dict[str, int]:
        deleted_ids = {int(item["grade_id"]) for item in self.ambiguous_reviews}
        tag_ids = {int(item["grade_id"]) for item in self.tagged_reviews}
        return {
            "ai_feedback_rows_archived": len(self.ai_feedback_rows),
            "ambiguous_review_rows_to_remove": len(self.ambiguous_reviews),
            "review_tags_to_swap": len(tag_ids - deleted_ids),
            "archive_rows": len(self.archive_payloads),
            "log_sources": len(self.log_sources),
        }


def _as_int(value: str) -> int | None:
    return None if value in {"None", "N/A"} else int(value)


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=timezone.utc)


def _event_base(
    *,
    event_type: str,
    occurred_at: datetime,
    source_name: str,
    source_sha256: str,
    source_line: int,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "occurred_at": occurred_at.isoformat(),
        "source_name": source_name,
        "source_sha256": source_sha256,
        "source_line": source_line,
    }


def parse_log_files(paths: Iterable[Path]) -> ParsedLogEvidence:
    """Parse sanitized correction evidence from complete retained grade logs.

    IP addresses, free-text review comments, and raw log lines are deliberately
    excluded from the archive payload.
    """
    review_events: dict[int, list[dict[str, Any]]] = defaultdict(list)
    consensus_events: dict[int, list[dict[str, Any]]] = defaultdict(list)
    ai_events: dict[int, list[dict[str, Any]]] = defaultdict(list)
    manifest: list[dict[str, Any]] = []

    for path in sorted(paths, key=lambda item: item.name):
        raw = path.read_bytes()
        source_sha256 = hashlib.sha256(raw).hexdigest()
        manifest.append(
            {
                "source_name": path.name,
                "sha256": source_sha256,
                "size_bytes": len(raw),
            }
        )
        for line_number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            timestamp_match = _TIMESTAMP_RE.match(line)
            if not timestamp_match:
                continue
            occurred_at = _parse_timestamp(timestamp_match.group("timestamp"))

            review_match = _REVIEW_RE.search(line)
            if review_match:
                event = _event_base(
                    event_type="human_review_submission",
                    occurred_at=occurred_at,
                    source_name=path.name,
                    source_sha256=source_sha256,
                    source_line=line_number,
                )
                event.update(
                    {
                        "actor_user_id": int(review_match.group("user_id")),
                        "task_id": int(review_match.group("task_id")),
                        "disease_id": int(review_match.group("disease_id")),
                        "submitted_disease_grading_id": _as_int(review_match.group("grade")),
                        "submission_type": review_match.group("event_type"),
                        "logged_grade_id": _as_int(review_match.group("grade_id")),
                    }
                )
                review_events[event["task_id"]].append(event)
                continue

            consensus_match = _CONSENSUS_RE.search(line)
            if consensus_match:
                event = _event_base(
                    event_type="consensus_override_via_review",
                    occurred_at=occurred_at,
                    source_name=path.name,
                    source_sha256=source_sha256,
                    source_line=line_number,
                )
                previous_method = consensus_match.group("prev_method").strip()
                event.update(
                    {
                        "actor_user_id": int(consensus_match.group("user_id")),
                        "task_id": int(consensus_match.group("task_id")),
                        "new_disease_grading_id": int(consensus_match.group("new_grade_id")),
                        "previous_method": None if previous_method == "None" else previous_method,
                        "previous_disease_grading_id": _as_int(
                            consensus_match.group("prev_grade_id")
                        ),
                    }
                )
                consensus_events[event["task_id"]].append(event)
                continue

            ai_header_match = _AI_HEADER_RE.search(line)
            if not ai_header_match:
                continue
            actor_user_id = int(ai_header_match.group("user_id"))
            task_id = int(ai_header_match.group("task_id"))
            for item_match in _AI_ITEM_RE.finditer(ai_header_match.group("body")):
                event = _event_base(
                    event_type="ai_feedback_submission",
                    occurred_at=occurred_at,
                    source_name=path.name,
                    source_sha256=source_sha256,
                    source_line=line_number,
                )
                status = item_match.group("status")
                event.update(
                    {
                        "actor_user_id": actor_user_id,
                        "task_id": task_id,
                        "ai_grade_id": int(item_match.group("grade_id")),
                        "status": None if status == "none" else status,
                        "model": item_match.group("model").strip(),
                    }
                )
                ai_events[event["ai_grade_id"]].append(event)

    sort_key = lambda event: (event["occurred_at"], event["source_name"], event["source_line"])
    return ParsedLogEvidence(
        review_events_by_task={
            key: tuple(sorted(value, key=sort_key)) for key, value in review_events.items()
        },
        consensus_events_by_task={
            key: tuple(sorted(value, key=sort_key)) for key, value in consensus_events.items()
        },
        ai_events_by_grade={
            key: tuple(sorted(value, key=sort_key)) for key, value in ai_events.items()
        },
        source_manifest=tuple(manifest),
    )


def discover_log_files(log_dir: Path) -> tuple[Path, ...]:
    paths = tuple(path for path in log_dir.glob("grades.log*") if path.is_file())
    if not paths:
        raise CorrectionInvariantError(f"No grades.log files found in {log_dir}")
    return paths


def _parse_db_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_datetime(event: Mapping[str, Any]) -> datetime:
    parsed = _parse_db_datetime(event["occurred_at"])
    if parsed is None:
        raise CorrectionInvariantError("Parsed event is missing occurred_at")
    return parsed


def _timestamps_match(left: object, right: object, *, tolerance_seconds: float = 2.0) -> bool:
    left_dt = _parse_db_datetime(left)
    right_dt = _parse_db_datetime(right)
    if left_dt is None or right_dt is None:
        return left_dt is right_dt
    return abs((left_dt - right_dt).total_seconds()) <= tolerance_seconds


def _fetch_json_rows(
    connection: Connection,
    sql: str,
    parameters: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        dict(row.payload)
        for row in connection.execute(text(sql), dict(parameters or {}))
    ]


def _find_source_grade(
    task_grades: Sequence[dict[str, Any]],
    *,
    method: str,
    disease_grading_id: int,
) -> tuple[int | None, str]:
    if method == "match":
        matching = [
            row
            for row in task_grades
            if row["role_slot"] in {"resident", "resident2"}
            and int(row["disease_grading_id"]) == disease_grading_id
        ]
        roles = {row["role_slot"] for row in matching}
        if roles != {"resident", "resident2"}:
            raise CorrectionInvariantError(
                f"Cannot prove match consensus for grade {disease_grading_id}; roles={sorted(roles)}"
            )
        decided_at = max(str(row["updated_at"] or row["created_at"]) for row in matching)
        return None, decided_at

    role = "arbitrator" if method == "adjudication" else "regrade_adj"
    matching = [
        row
        for row in task_grades
        if row["role_slot"] == role and int(row["disease_grading_id"]) == disease_grading_id
    ]
    if len(matching) != 1:
        raise CorrectionInvariantError(
            f"Cannot prove {method} consensus for grade {disease_grading_id}; {len(matching)} sources"
        )
    row = matching[0]
    return int(row["grader_user_id"]), str(row["updated_at"] or row["created_at"])


def _build_restored_consensus(
    connection: Connection,
    *,
    task_id: int,
    first_override: Mapping[str, Any],
) -> dict[str, Any]:
    method = first_override.get("previous_method")
    grade_id = first_override.get("previous_disease_grading_id")
    if method not in {"match", "adjudication", "regrade"} or not isinstance(grade_id, int):
        raise CorrectionInvariantError(
            f"Task {task_id}: earliest retained review override does not expose a restorable consensus"
        )

    task_grades = _fetch_json_rows(
        connection,
        "SELECT to_jsonb(g) AS payload FROM grades g "
        "WHERE g.task_id = :task_id AND g.role_slot IN "
        "('resident','resident2','arbitrator','regrade_adj') ORDER BY g.id",
        {"task_id": task_id},
    )
    decided_by_user_id, decided_at = _find_source_grade(
        task_grades,
        method=method,
        disease_grading_id=grade_id,
    )
    label = connection.execute(
        text(
            "SELECT d.name AS disease_name, dg.impression AS grade_name, "
            "dg.guidelines AS grade_description "
            "FROM grading_tasks t "
            "JOIN diseases d ON d.id = t.disease_id "
            "JOIN disease_gradings dg ON dg.id = :grade_id AND dg.disease_id = t.disease_id "
            "WHERE t.id = :task_id"
        ),
        {"grade_id": grade_id, "task_id": task_id},
    ).mappings().one_or_none()
    if label is None:
        raise CorrectionInvariantError(
            f"Task {task_id}: prior disease grading {grade_id} does not match the task disease"
        )
    return {
        "final_disease_grading_id": grade_id,
        "method": method,
        "decided_by_user_id": decided_by_user_id,
        "decided_at": decided_at,
        "final_disease_name": label["disease_name"],
        "final_grade_name": label["grade_name"],
        "final_grade_description": label["grade_description"],
    }


def _swap_influence_tag(comment: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return f"AI influence: {'no' if match.group(1).lower() == 'yes' else 'yes'}"

    return _INFLUENCE_RE.sub(replace, comment)


def _source_refs(events: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    refs = {
        (str(event["source_name"]), str(event["source_sha256"]))
        for event in events
    }
    return [
        {"source_name": source_name, "sha256": sha256}
        for source_name, sha256 in sorted(refs)
    ]


def build_correction_plan(connection: Connection, log_dir: Path = DEFAULT_LOG_DIR) -> CorrectionPlan:
    """Reconcile logs and relational state without mutating the database."""
    ai_rows = _fetch_json_rows(
        connection,
        "SELECT to_jsonb(g) AS payload FROM grades g WHERE g.role_slot = 'ai' "
        "AND (g.ai_review_status IS NOT NULL OR g.ai_review_comment IS NOT NULL "
        "OR g.ai_reviewed_by_user_id IS NOT NULL OR g.ai_reviewed_at IS NOT NULL) ORDER BY g.id",
    )
    review_rows = _fetch_json_rows(
        connection,
        "SELECT to_jsonb(g) AS payload FROM grades g WHERE g.role_slot = 'review' ORDER BY g.id",
    )
    if not ai_rows and not review_rows:
        return CorrectionPlan((), (), (), (), ())

    evidence = parse_log_files(discover_log_files(log_dir))
    archive_by_grade: dict[int, dict[str, Any]] = {}

    for row in ai_rows:
        grade_id = int(row["id"])
        events = list(evidence.ai_events_by_grade.get(grade_id, ()))
        if not events:
            raise CorrectionInvariantError(f"AI grade {grade_id}: no retained feedback event")
        latest = events[-1]
        current_status = str(row["ai_review_status"]).lower() if row["ai_review_status"] else None
        if (
            int(latest["task_id"]) != int(row["task_id"])
            or int(latest["actor_user_id"]) != int(row["ai_reviewed_by_user_id"])
            or latest["status"] != current_status
            or not _timestamps_match(latest["occurred_at"], row["ai_reviewed_at"])
        ):
            raise CorrectionInvariantError(
                f"AI grade {grade_id}: latest retained event does not match current feedback state"
            )
        archive_by_grade[grade_id] = {
            "correction_version": CORRECTION_VERSION,
            "record_kind": "ai_feedback_audit",
            "original_grade": row,
            "actions": ["archive_structured_ai_feedback_history"],
            "evidence": {
                "ai_feedback_events": events,
                "sources": _source_refs(events),
            },
        }

    ambiguous: list[dict[str, Any]] = []
    tagged: list[dict[str, Any]] = []
    for row in review_rows:
        grade_id = int(row["id"])
        task_id = int(row["task_id"])
        human_events = [
            event
            for event in evidence.review_events_by_task.get(task_id, ())
            if event["submitted_disease_grading_id"] is not None
        ]
        latest = human_events[-1] if human_events else None
        is_current_event = bool(
            latest
            and int(latest["submitted_disease_grading_id"]) == int(row["disease_grading_id"])
            and not (
                latest["logged_grade_id"] is not None
                and int(latest["logged_grade_id"]) != grade_id
            )
            and _timestamps_match(latest["occurred_at"], row["updated_at"])
        )
        is_ambiguous = bool(
            is_current_event and int(latest["actor_user_id"]) != int(row["grader_user_id"])
        )
        has_tag = bool(row.get("comment") and _INFLUENCE_RE.search(str(row["comment"])))

        if not is_ambiguous and not has_tag:
            continue
        if latest is None or not is_current_event:
            raise CorrectionInvariantError(
                f"Review grade {grade_id}: retained submission does not match current row"
            )

        consensus_events = list(evidence.consensus_events_by_task.get(task_id, ()))
        related_events = [*human_events, *consensus_events]
        payload: dict[str, Any] = {
            "correction_version": CORRECTION_VERSION,
            "record_kind": "human_review_correction",
            "original_grade": row,
            "actions": [],
            "evidence": {
                "human_review_events": human_events,
                "consensus_override_events": consensus_events,
                "sources": _source_refs(related_events),
            },
        }

        if has_tag:
            corrected_comment = _swap_influence_tag(str(row["comment"]))
            payload["actions"].append("swap_reversed_ai_influence_tag")
            payload["corrected_comment"] = corrected_comment
            tagged.append(
                {
                    "grade_id": grade_id,
                    "task_id": task_id,
                    "original_comment": row["comment"],
                    "corrected_comment": corrected_comment,
                }
            )

        if is_ambiguous:
            if not consensus_events:
                raise CorrectionInvariantError(
                    f"Review grade {grade_id}: no retained consensus override event"
                )
            consensus_before_row = connection.execute(
                text("SELECT to_jsonb(c) AS payload FROM consensus c WHERE c.task_id = :task_id"),
                {"task_id": task_id},
            ).one_or_none()
            if consensus_before_row is None:
                raise CorrectionInvariantError(f"Task {task_id}: current consensus is missing")
            consensus_before = dict(consensus_before_row.payload)
            if (
                consensus_before["method"] != "task_review"
                or int(consensus_before["final_disease_grading_id"])
                != int(row["disease_grading_id"])
            ):
                raise CorrectionInvariantError(
                    f"Task {task_id}: current consensus is not the ambiguous review grade"
                )
            consensus_after = _build_restored_consensus(
                connection,
                task_id=task_id,
                first_override=consensus_events[0],
            )
            payload["actions"].extend(
                ["remove_ambiguous_human_review", "restore_pre_review_consensus"]
            )
            payload["attribution_mismatch"] = {
                "stored_grader_user_id": int(row["grader_user_id"]),
                "latest_submission_actor_user_id": int(latest["actor_user_id"]),
                "latest_submission_at": latest["occurred_at"],
            }
            payload["consensus_before"] = consensus_before
            payload["consensus_after"] = consensus_after
            ambiguous.append(
                {
                    "grade_id": grade_id,
                    "task_id": task_id,
                    "consensus_before": consensus_before,
                    "consensus_after": consensus_after,
                }
            )

        archive_by_grade[grade_id] = payload

    return CorrectionPlan(
        ai_feedback_rows=tuple(ai_rows),
        ambiguous_reviews=tuple(ambiguous),
        tagged_reviews=tuple(tagged),
        archive_payloads=tuple(
            {"grade_id": grade_id, "payload": payload}
            for grade_id, payload in sorted(archive_by_grade.items())
        ),
        log_sources=evidence.source_manifest,
    )


def _archive_payload(
    connection: Connection,
    *,
    grade_id: int,
    payload: Mapping[str, Any],
) -> None:
    original_grade = payload["original_grade"]
    connection.execute(
        text(
            "INSERT INTO review_grade_correction_archive "
            "(original_grade_id, task_id, migration_id, script_name, payload_json) "
            "VALUES (:grade_id, :task_id, :migration_id, :script_name, CAST(:payload AS jsonb)) "
            "ON CONFLICT (migration_id, original_grade_id) DO NOTHING"
        ),
        {
            "grade_id": grade_id,
            "task_id": int(original_grade["task_id"]),
            "migration_id": MIGRATION_ID,
            "script_name": SCRIPT_NAME,
            "payload": json.dumps(payload, sort_keys=True),
        },
    )


def _update_consensus(connection: Connection, task_id: int, snapshot: Mapping[str, Any]) -> None:
    connection.execute(
        text(
            "UPDATE consensus SET final_disease_grading_id=:grade_id, method=:method, "
            "decided_by_user_id=:decided_by, decided_at=:decided_at, "
            "final_disease_name=:disease_name, final_grade_name=:grade_name, "
            "final_grade_description=:grade_description WHERE task_id=:task_id"
        ),
        {
            "task_id": task_id,
            "grade_id": snapshot["final_disease_grading_id"],
            "method": snapshot["method"],
            "decided_by": snapshot["decided_by_user_id"],
            "decided_at": snapshot["decided_at"],
            "disease_name": snapshot["final_disease_name"],
            "grade_name": snapshot["final_grade_name"],
            "grade_description": snapshot["final_grade_description"],
        },
    )


def _load_existing_archive(connection: Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            "SELECT original_grade_id, payload_json FROM review_grade_correction_archive "
            "WHERE migration_id=:migration_id ORDER BY original_grade_id"
        ),
        {"migration_id": MIGRATION_ID},
    )
    return [
        {"grade_id": int(row.original_grade_id), "payload": dict(row.payload_json)}
        for row in rows
    ]


def _apply_archived_actions(connection: Connection, entries: Sequence[dict[str, Any]]) -> None:
    for entry in entries:
        grade_id = int(entry["grade_id"])
        payload = entry["payload"]
        actions = set(payload.get("actions", []))
        original_grade = payload["original_grade"]
        current = connection.execute(
            text("SELECT to_jsonb(g) AS payload FROM grades g WHERE g.id=:grade_id"),
            {"grade_id": grade_id},
        ).one_or_none()

        if "remove_ambiguous_human_review" in actions:
            if current is not None and dict(current.payload) != original_grade:
                raise CorrectionInvariantError(
                    f"Review grade {grade_id}: row changed after archival; refusing removal"
                )
            if current is not None:
                _update_consensus(connection, int(original_grade["task_id"]), payload["consensus_after"])
                connection.execute(text("DELETE FROM grades WHERE id=:grade_id"), {"grade_id": grade_id})
            continue

        if "swap_reversed_ai_influence_tag" in actions:
            if current is None:
                raise CorrectionInvariantError(f"Review grade {grade_id}: row missing before tag correction")
            current_comment = current.payload.get("comment")
            corrected_comment = payload["corrected_comment"]
            if current_comment == corrected_comment:
                continue
            if current_comment != original_grade.get("comment"):
                raise CorrectionInvariantError(
                    f"Review grade {grade_id}: comment changed after archival; refusing tag correction"
                )
            connection.execute(
                text("UPDATE grades SET comment=:comment WHERE id=:grade_id"),
                {"comment": corrected_comment, "grade_id": grade_id},
            )


def apply_correction(
    connection: Connection,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> dict[str, int | str]:
    """Archive evidence and apply the proven correction in the caller transaction."""
    existing = _load_existing_archive(connection)
    if existing:
        _apply_archived_actions(connection, existing)
        return {"state": "reapplied_from_archive", "archive_rows": len(existing)}

    plan = build_correction_plan(connection, log_dir)
    summary: dict[str, int | str] = {"state": "no_data", **plan.summary()}
    if not plan.archive_payloads:
        return summary

    for entry in plan.archive_payloads:
        _archive_payload(
            connection,
            grade_id=int(entry["grade_id"]),
            payload=entry["payload"],
        )
    archived_count = connection.execute(
        text(
            "SELECT count(*) FROM review_grade_correction_archive "
            "WHERE migration_id=:migration_id"
        ),
        {"migration_id": MIGRATION_ID},
    ).scalar_one()
    if int(archived_count) != len(plan.archive_payloads):
        raise CorrectionInvariantError(
            f"Archive verification failed: expected {len(plan.archive_payloads)}, found {archived_count}"
        )

    _apply_archived_actions(connection, list(plan.archive_payloads))
    remaining_ambiguous = connection.execute(
        text("SELECT count(*) FROM grades WHERE id = ANY(CAST(:grade_ids AS integer[]))"),
        {"grade_ids": [int(item["grade_id"]) for item in plan.ambiguous_reviews]},
    ).scalar_one() if plan.ambiguous_reviews else 0
    if int(remaining_ambiguous) != 0:
        raise CorrectionInvariantError("One or more ambiguous review rows remained after correction")

    return {"state": "applied", **plan.summary()}


def _restore_grade(connection: Connection, original_grade: Mapping[str, Any]) -> None:
    connection.execute(
        text(
            "INSERT INTO grades SELECT * FROM jsonb_populate_record(NULL::grades, CAST(:payload AS jsonb))"
        ),
        {"payload": json.dumps(original_grade, sort_keys=True)},
    )


def revert_correction(connection: Connection) -> dict[str, int | str]:
    """Safely restore corrected rows while retaining the immutable archive."""
    entries = _load_existing_archive(connection)
    restored = 0
    tag_reverted = 0
    for entry in entries:
        grade_id = int(entry["grade_id"])
        payload = entry["payload"]
        actions = set(payload.get("actions", []))
        original_grade = payload["original_grade"]

        if "remove_ambiguous_human_review" in actions:
            replacement_count = connection.execute(
                text(
                    "SELECT count(*) FROM grades WHERE task_id=:task_id AND role_slot='review'"
                ),
                {"task_id": int(original_grade["task_id"])},
            ).scalar_one()
            if int(replacement_count):
                raise CorrectionInvariantError(
                    f"Task {original_grade['task_id']}: a replacement review exists; refusing downgrade"
                )
            current_consensus = connection.execute(
                text("SELECT to_jsonb(c) AS payload FROM consensus c WHERE c.task_id=:task_id"),
                {"task_id": int(original_grade["task_id"])},
            ).one()
            current_payload = dict(current_consensus.payload)
            for key, expected in payload["consensus_after"].items():
                if str(current_payload.get(key)) != str(expected):
                    raise CorrectionInvariantError(
                        f"Task {original_grade['task_id']}: consensus changed; refusing downgrade"
                    )
            _restore_grade(connection, original_grade)
            _update_consensus(
                connection,
                int(original_grade["task_id"]),
                payload["consensus_before"],
            )
            restored += 1
            continue

        if "swap_reversed_ai_influence_tag" in actions:
            current = connection.execute(
                text("SELECT comment FROM grades WHERE id=:grade_id"),
                {"grade_id": grade_id},
            ).one_or_none()
            if current is None or current.comment != payload["corrected_comment"]:
                raise CorrectionInvariantError(
                    f"Review grade {grade_id}: corrected comment changed; refusing downgrade"
                )
            connection.execute(
                text("UPDATE grades SET comment=:comment WHERE id=:grade_id"),
                {"comment": original_grade.get("comment"), "grade_id": grade_id},
            )
            tag_reverted += 1

    return {
        "state": "reverted",
        "review_rows_restored": restored,
        "review_tags_reverted": tag_reverted,
        "archive_rows_retained": len(entries),
    }


def refresh_image_listing_materialized_views(connection: Connection) -> int:
    """Refresh only validated per-disease image-listing materialized views."""
    names = connection.execute(
        text(
            "SELECT matviewname FROM pg_matviews WHERE schemaname=current_schema() "
            "AND matviewname LIKE 'mvw_image_listing_%_v2' ORDER BY matviewname"
        )
    ).scalars()
    count = 0
    preparer = connection.dialect.identifier_preparer
    for name in names:
        if not _SAFE_MATVIEW_RE.fullmatch(name):
            raise CorrectionInvariantError(f"Unexpected materialized-view name: {name}")
        connection.execute(text(f"REFRESH MATERIALIZED VIEW {preparer.quote(name)}"))
        count += 1
    return count


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="required safety flag")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("Writes are migration-only; pass --dry-run for a read-only preview")

    from db_transaction_manager import transaction_scope

    with transaction_scope() as session:
        plan = build_correction_plan(session.connection(), args.log_dir)
        print(json.dumps(plan.summary(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
