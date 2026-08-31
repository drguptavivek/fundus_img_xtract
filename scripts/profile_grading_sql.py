"""Per-statement profile of the /grading dashboard KPI path.

Separates the two costs the cumulative profiler conflates:
  * database time  - how long Postgres took
  * hydration time - how long SQLAlchemy took turning rows into objects

Usage (inside the web container):
    uv run python -m scripts.profile_grading_sql [user_id] [--explain]
"""

from __future__ import annotations

import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from sqlalchemy import event, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models import Session, User  # noqa: E402
from utils.dualGradingKPIs import (  # noqa: E402
    get_user_kpi_pending_task_count_data,
)


def shape(sql: str) -> str:
    """Collapse a statement to its shape so repeats group together."""
    s = " ".join(sql.split())
    s = re.sub(r"IN \([^)]*\)", "IN (...)", s)
    s = re.sub(r"\b\d+\b", "?", s)
    s = re.sub(r"%\(\w+\)s", "?", s)
    return s


def first_table(sql: str) -> str:
    m = re.search(r"\bFROM\s+([a-zA-Z_][\w.]*)", sql)
    return m.group(1) if m else "?"


class Recorder:
    def __init__(self, session):
        self.session = session
        self.rows = []
        self._t0 = {}

    def _before(self, conn, cursor, statement, params, context, executemany):
        self._t0[id(context)] = time.perf_counter()

    def _after(self, conn, cursor, statement, params, context, executemany):
        t0 = self._t0.pop(id(context), None)
        if t0 is None:
            return
        dt = time.perf_counter() - t0
        try:
            n = cursor.rowcount
        except Exception:
            n = -1
        self.rows.append((statement, dt, n, params))

    def __enter__(self):
        e = self.session.get_bind()
        event.listen(e, "before_cursor_execute", self._before)
        event.listen(e, "after_cursor_execute", self._after)
        return self

    def __exit__(self, *exc):
        e = self.session.get_bind()
        event.remove(e, "before_cursor_execute", self._before)
        event.remove(e, "after_cursor_execute", self._after)
        return False


def main(argv):
    explain = "--explain" in argv
    argv = [a for a in argv if not a.startswith("--")]
    user_id = int(argv[0]) if argv else 1

    db = Session()
    try:
        user = db.get(User, user_id)
        print(f"user {user_id} ({getattr(user,'username','?')})  exclude_enforced=True\n")

        # Warm caches so steady-state is measured.
        get_user_kpi_pending_task_count_data(
            db, user_id, exclude_project_encounter_sets=True
        )
        db.expire_all()

        with Recorder(db) as rec:
            t0 = time.perf_counter()
            get_user_kpi_pending_task_count_data(
                db, user_id, exclude_project_encounter_sets=True
            )
            wall = time.perf_counter() - t0

        db_time = sum(r[1] for r in rec.rows)
        total_rows = sum(r[2] for r in rec.rows if r[2] > 0)
        print(f"wall            {wall:8.3f}s")
        print(f"database time   {db_time:8.3f}s  ({db_time/wall*100:4.1f}%)")
        print(f"python time     {wall-db_time:8.3f}s  ({(wall-db_time)/wall*100:4.1f}%)")
        print(f"statements      {len(rec.rows):8d}")
        print(f"rows returned   {total_rows:8d}\n")

        agg = defaultdict(
            lambda: {"n": 0, "t": 0.0, "rows": 0, "sql": "", "params": None}
        )
        for sql, dt, n, params in rec.rows:
            k = shape(sql)
            a = agg[k]
            a["n"] += 1
            a["t"] += dt
            a["rows"] += max(n, 0)
            a["sql"] = sql
            a["params"] = params

        ranked = sorted(agg.values(), key=lambda a: a["t"], reverse=True)
        print("=" * 100)
        print(f"{'db_time':>9} {'calls':>6} {'rows':>8} {'cols':>6}  table")
        print("=" * 100)
        for a in ranked[:12]:
            tbl = first_table(a["sql"])
            ncols = a["sql"].count(" AS ")
            print(
                f"{a['t']:8.3f}s {a['n']:6d} {a['rows']:8d} {ncols:6d}  {tbl}"
            )
            print(f"           {' '.join(a['sql'].split())[:130]}")
            print()

        if explain and ranked:
            print("=" * 100)
            print("EXPLAIN ANALYZE of the single costliest statement shape")
            print("=" * 100)
            for a in ranked[:3]:
                print(f"\n--- {a['t']:.3f}s over {a['n']} calls, {a['rows']} rows ---")
                raw = db.connection().connection
                cur = raw.cursor()
                try:
                    cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + a["sql"], a["params"])
                    for row in cur.fetchall():
                        print("  " + row[0])
                except Exception as exc:
                    print(f"  (explain failed: {type(exc).__name__}: {exc})")
                finally:
                    cur.close()
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
