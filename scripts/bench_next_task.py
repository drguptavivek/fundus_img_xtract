"""Benchmark Save & Next task acquisition.

Phase 0 baseline for docs/15-DEVELOPMENT/grader_responsiveness_performance_plan.md (D2).

``grading.workbench.queue.select_next_task`` sorts the entire eligible candidate
set by ``random()`` with no LIMIT, hydrates it all, then walks it in Python. This
measures the resulting wall time, SQL time, and candidate-set size per
(user, disease, role_slot) queue.

Usage (inside the web container):
    uv run python -m scripts.bench_next_task [user_id ...]

Read-only: the surrounding transaction is rolled back so no lease is retained.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import event, func, select

# Ensure project root is importable when invoked as a module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models import (  # noqa: E402
    Disease,
    GradingTask,
    Session,
    User,
    UserDiseaseUnitRole,
)
from grading.workbench import queue as queue_mod  # noqa: E402

ROLE_SLOTS = ("resident", "resident2", "arbitrator")


class Probe:
    """Count statements and record how many rows the unbounded fetch returned."""

    def __init__(self, session):
        self.session = session
        self.count = 0
        self.sql_time = 0.0
        self.random_sorts = 0
        self._start = {}

    def _before(self, conn, cursor, statement, params, context, executemany):
        self._start[id(context)] = time.perf_counter()
        if "random()" in statement:
            self.random_sorts += 1

    def _after(self, conn, cursor, statement, params, context, executemany):
        began = self._start.pop(id(context), None)
        if began is not None:
            self.sql_time += time.perf_counter() - began
        self.count += 1

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
        select(UserDiseaseUnitRole.user_id).where(
            UserDiseaseUnitRole.active.is_(True)
        )
    ).scalars().all()
    return [uid for uid, _ in Counter(rows).most_common(limit)]


def user_queues(db, user_id):
    """Every (disease_id, role_slot) this user could pull work from."""
    roles = (
        db.query(UserDiseaseUnitRole)
        .filter(
            UserDiseaseUnitRole.user_id == user_id,
            UserDiseaseUnitRole.active.is_(True),
        )
        .all()
    )
    seen = set()
    for role in roles:
        for slot, allowed in (
            ("resident", role.can_grade_resident),
            ("resident2", role.can_grade_resident2),
            ("arbitrator", role.can_arbitrate),
        ):
            if allowed and (role.disease_id, slot) not in seen:
                seen.add((role.disease_id, slot))
                yield role.disease_id, slot


def main(argv):
    db = Session()
    try:
        user_ids = [int(a) for a in argv] or pick_users(db)
        disease_names = {
            d.id: d.name for d in db.query(Disease).all()
        }

        for user_id in user_ids:
            user = db.get(User, user_id)
            label = getattr(user, "username", None) or f"id={user_id}"
            print(f"\n=== user {user_id} ({label}) ===")
            queues = list(user_queues(db, user_id))
            if not queues:
                print("  no eligible queues")
                continue

            for disease_id, role_slot in queues:
                db.expire_all()
                with Probe(db) as probe:
                    began = time.perf_counter()
                    try:
                        task = queue_mod.select_next_task(
                            db,
                            user_id=user_id,
                            disease_id=disease_id,
                            role_slot=role_slot,
                            lab_unit_id=None,
                        )
                        err = None
                    except Exception as exc:  # noqa: BLE001 - benchmark surface
                        task, err = None, f"{type(exc).__name__}: {exc}"
                    wall = time.perf_counter() - began
                # Never keep the FOR UPDATE lease this probe may have taken.
                db.rollback()

                dname = disease_names.get(disease_id, disease_id)
                outcome = err or ("task" if task is not None else "empty")
                print(
                    f"  {dname[:28]:28s} {role_slot:10s} "
                    f"wall={wall:7.3f}s sql={probe.sql_time:7.3f}s "
                    f"queries={probe.count:4d} random_sorts={probe.random_sorts} "
                    f"-> {outcome}"
                )
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
