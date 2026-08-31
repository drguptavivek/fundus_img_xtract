"""Benchmark the /grading dashboard KPI path.

Phase 0 baseline for docs/15-DEVELOPMENT/grader_responsiveness_performance_plan.md (D12).

Usage (inside the web container):
    uv run python -m scripts.bench_grading_kpis [user_id ...]

With no user ids, picks the users holding the most active UserDiseaseUnitRole rows.
Reports wall time and SQL query count for the pending-KPI call, which is the
branch that materializes the pending queue when any project has allocation
enforcement enabled.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import event, select

# Ensure project root is importable when invoked as a module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models import Session, User, UserDiseaseUnitRole  # noqa: E402
from utils.dualGradingKPIs import (  # noqa: E402
    get_user_kpi_pending_task_count_data,
)


class QueryCounter:
    """Count and time statements issued on a session's connection."""

    def __init__(self, session):
        self.session = session
        self.statements = Counter()
        self.count = 0
        self.sql_time = 0.0
        self._start = {}

    def _before(self, conn, cursor, statement, params, context, executemany):
        self._start[id(context)] = time.perf_counter()

    def _after(self, conn, cursor, statement, params, context, executemany):
        began = self._start.pop(id(context), None)
        if began is not None:
            self.sql_time += time.perf_counter() - began
        self.count += 1
        self.statements[statement.split("\n", 1)[0][:110]] += 1

    def __enter__(self):
        engine = self.session.get_bind()
        event.listen(engine, "before_cursor_execute", self._before)
        event.listen(engine, "after_cursor_execute", self._after)
        return self

    def __exit__(self, *exc):
        engine = self.session.get_bind()
        event.remove(engine, "before_cursor_execute", self._before)
        event.remove(engine, "after_cursor_execute", self._after)
        return False


def pick_users(db, limit=3):
    rows = db.execute(
        select(UserDiseaseUnitRole.user_id)
        .where(UserDiseaseUnitRole.active.is_(True))
    ).scalars().all()
    ranked = [uid for uid, _ in Counter(rows).most_common(limit)]
    return ranked


def bench(db, user_id, *, exclude_enforced):
    with QueryCounter(db) as qc:
        began = time.perf_counter()
        data = get_user_kpi_pending_task_count_data(
            db,
            user_id,
            exclude_project_encounter_sets=exclude_enforced,
        )
        wall = time.perf_counter() - began
    return wall, qc, data, _sum_ints(data)


def _sum_ints(value):
    """Total every int leaf, whatever nesting depth the KPI payload uses."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        return sum(_sum_ints(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return sum(_sum_ints(v) for v in value)
    return 0


def main(argv):
    db = Session()
    try:
        user_ids = [int(a) for a in argv] or pick_users(db)
        if not user_ids:
            print("no users with active disease-unit roles; nothing to benchmark")
            return 1

        for user_id in user_ids:
            user = db.get(User, user_id)
            label = getattr(user, "username", None) or f"id={user_id}"
            print(f"\n=== user {user_id} ({label}) ===")
            for exclude_enforced in (True, False):
                # Fresh identity map so ORM caching does not flatter a re-run.
                db.expire_all()
                wall, qc, data, total = bench(
                    db, user_id, exclude_enforced=exclude_enforced
                )
                print(
                    f"  exclude_enforced={str(exclude_enforced):5s} "
                    f"wall={wall:7.3f}s  sql={qc.sql_time:7.3f}s  "
                    f"queries={qc.count:5d}  diseases={len(data):2d}  "
                    f"summed_kpis={total}"
                )
                for stmt, n in qc.statements.most_common(3):
                    if n > 1:
                        print(f"      {n:5d}x {stmt}")
                print(f"      kpis={data}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
