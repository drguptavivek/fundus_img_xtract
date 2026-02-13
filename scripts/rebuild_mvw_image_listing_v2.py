"""Rebuild per-disease mvw_image_listing_*_v2 materialized views.

Examples:
  # Drop + create + refresh (default)
  docker compose exec web uv run python scripts/rebuild_mvw_image_listing_v2.py

  # Drop only
  docker compose exec web uv run python scripts/rebuild_mvw_image_listing_v2.py --drop

  # Create only
  docker compose exec web uv run python scripts/rebuild_mvw_image_listing_v2.py --create

  # Refresh only
  docker compose exec web uv run python scripts/rebuild_mvw_image_listing_v2.py --refresh
"""

from __future__ import annotations

import os
import sys

import argparse
import logging

from sqlalchemy import text

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db_transaction_manager import transaction_scope
from utils.mvw_image_listing_v2 import ensure_per_disease_image_listing_mvs

_LOGGER = logging.getLogger("mvw_image_listing_v2_rebuild")


def _drop_v2_views() -> int:
    with transaction_scope() as db:
        rows = db.execute(
            text("SELECT matviewname FROM pg_matviews WHERE matviewname LIKE :pattern"),
            {"pattern": "mvw_image_listing_%_v2"},
        ).all()
        names = [row[0] for row in rows]

        for name in names:
            quoted = db.execute(text("SELECT quote_ident(:name)"), {"name": name}).scalar()
            db.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {quoted}"))

    return len(names)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drop, recreate, and refresh per-disease mvw_image_listing_*_v2 materialized views."
    )
    parser.add_argument("--drop", action="store_true", help="Drop existing v2 materialized views.")
    parser.add_argument("--create", action="store_true", help="Create missing v2 materialized views.")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing v2 materialized views.")
    args = parser.parse_args()

    run_all = not (args.drop or args.create or args.refresh)
    do_drop = args.drop or run_all
    do_create = args.create or run_all
    do_refresh = args.refresh or run_all

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logging.getLogger("materialized_view_v2").setLevel(logging.INFO)

    if do_drop:
        _LOGGER.info("Dropping v2 materialized views...")
        dropped = _drop_v2_views()
        _LOGGER.info("Dropped %s v2 materialized views.", dropped)

    if do_create:
        _LOGGER.info("Creating missing v2 materialized views...")
        result = ensure_per_disease_image_listing_mvs(create_missing=True, refresh_existing=False)
        _LOGGER.info("Create result: %s", result)

    if do_refresh:
        _LOGGER.info("Refreshing v2 materialized views...")
        result = ensure_per_disease_image_listing_mvs(create_missing=False, refresh_existing=True)
        _LOGGER.info("Refresh result: %s", result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
