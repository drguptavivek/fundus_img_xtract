#!/usr/bin/env python3
"""
Initialize (drop & recreate) the direct_image_uploads table for SQLite.

- Requires your project's models.py to define:
  - Base, engine
  - DirectImageUpload (with CHECKs & Indexes)
  - DIRECT_UPLOAD_DIR (Path)

Usage:
  python scripts/init_direct_image_uploads.py
"""

import os
import sys
from pathlib import Path

# Resolve project root: this file lives in <root>/scripts/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Optional: load .env if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Import your app models (must include DirectImageUpload)
from models import Base, engine, DIRECT_UPLOAD_DIR  # type: ignore
from models import DirectImageUpload  # noqa: F401 - ensures the model is registered


def ensure_sqlite_pragmas(eng: Engine) -> None:
    """Set useful SQLite PRAGMAs for schema ops."""
    with eng.connect() as conn:
        # Enforce FK constraints
        conn.execute(text("PRAGMA foreign_keys = ON"))
        # (Optional) Slightly safer writes during init
        conn.execute(text("PRAGMA journal_mode = WAL"))
        conn.commit()


def recreate_table(eng: Engine) -> None:
    """Drop & recreate only the direct_image_uploads table."""
    # Drop if exists (safe because you said there's no data)
    DirectImageUpload.__table__.drop(eng, checkfirst=True)
    # Recreate with all constraints & indexes defined on the model
    Base.metadata.create_all(eng, tables=[DirectImageUpload.__table__])


def ensure_dirs() -> None:
    """Make sure the direct uploads root exists."""
    try:
        DIRECT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise SystemExit(f"Failed to create DIRECT_UPLOAD_DIR at {DIRECT_UPLOAD_DIR}: {e}")


def verify_schema(eng: Engine) -> None:
    """Basic sanity check: list columns & indexes (SQLite)."""
    with eng.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(direct_image_uploads)")).fetchall()
        idxs = conn.execute(text("PRAGMA index_list(direct_image_uploads)")).fetchall()
        checks = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='direct_image_uploads'")).fetchone()

    print("\n[direct_image_uploads] columns:")
    for c in cols:
        # cid, name, type, notnull, dflt_value, pk
        print(f"  - {c[1]} {c[2]}{' NOT NULL' if c[3] else ''}{' [PK]' if c[5] else ''}")

    print("\n[direct_image_uploads] indexes:")
    for i in idxs:
        # seq, name, unique, origin, partial
        print(f"  - {i[1]} (unique={bool(i[2])})")

    print("\n[direct_image_uploads] create SQL (with CHECKs):")
    if checks and checks[0]:
        print(checks[0])
    else:
        print("  <no SQL returned>")


def main() -> None:
    print(f"Project root: {ROOT}")
    print("Ensuring SQLite PRAGMAs...")
    ensure_sqlite_pragmas(engine)

    print("Ensuring upload directory exists...")
    ensure_dirs()

    print("Recreating table: direct_image_uploads ...")
    recreate_table(engine)

    print("Verifying schema...")
    verify_schema(engine)

    print("\n✅ Done. The direct_image_uploads table is ready.")


if __name__ == "__main__":
    main()
