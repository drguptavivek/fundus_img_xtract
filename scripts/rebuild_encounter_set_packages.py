"""Preview/apply rebuilding every package that currently has a set-level task.

Preview (default):
  uv run python scripts/rebuild_encounter_set_packages.py

Apply only with the exact token emitted by the preview:
  uv run python scripts/rebuild_encounter_set_packages.py --apply \
    --confirm-token REBUILD-...

Exercise the full apply and force a rollback:
  uv run python scripts/rebuild_encounter_set_packages.py --validate-apply \
    --confirm-token REBUILD-...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_transaction_manager import transaction_scope
from encounter_sets.package_repair import (
    apply_set_package_rebuild,
    preview_set_package_rebuild,
)
from verify_encounter_set.routes import (
    _active_encounter_set_type_config,
    _create_verified_encounter_set_tasks,
    _encounter_set_package_configs,
)


def _resolve_policy(db, encounter):
    config = _active_encounter_set_type_config(encounter)
    return _encounter_set_package_configs(db, config, encounter)


def _create_current_tasks(db, encounter, preserved_task_ids: frozenset[int]) -> int:
    return _create_verified_encounter_set_tasks(
        db,
        encounter,
        create_negative_controls=False,
        adopt_unscoped_task_ids=preserved_task_ids,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply the rebuild in one transaction; default is read-only preview.",
    )
    mode.add_argument(
        "--validate-apply",
        action="store_true",
        help="Run the complete rebuild and all checks, then force a rollback.",
    )
    parser.add_argument(
        "--confirm-token",
        help="Exact population token printed by the latest preview.",
    )
    args = parser.parse_args()
    if (args.apply or args.validate_apply) and not args.confirm_token:
        parser.error("apply and validation modes require a fresh --confirm-token")
    if not (args.apply or args.validate_apply) and args.confirm_token:
        parser.error("--confirm-token is only valid with an apply mode")

    if not (args.apply or args.validate_apply):
        with transaction_scope() as db:
            preview = preview_set_package_rebuild(
                db,
                policy_resolver=_resolve_policy,
            )
            print(json.dumps({"mode": "preview", **preview.as_dict()}, indent=2))
        return 0

    try:
        with transaction_scope() as db:
            result = apply_set_package_rebuild(
                db,
                confirmation_token=args.confirm_token,
                policy_resolver=_resolve_policy,
                task_creator=_create_current_tasks,
            )
            if args.validate_apply:
                raise _ValidationRollback(result)
            print(json.dumps({"mode": "apply", **result.as_dict()}, indent=2))
    except _ValidationRollback as rollback:
        print(
            json.dumps(
                {"mode": "validate_apply_rolled_back", **rollback.result.as_dict()},
                indent=2,
            )
        )
    return 0


class _ValidationRollback(Exception):
    def __init__(self, result):
        super().__init__("Rollback-only validation completed.")
        self.result = result


if __name__ == "__main__":
    raise SystemExit(main())
