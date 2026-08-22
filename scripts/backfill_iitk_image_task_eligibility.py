"""Preview or apply IITK clinical-image grading task eligibility repair.

Preview (default):
  uv run python scripts/backfill_iitk_image_task_eligibility.py --project-id 5

Apply only with the exact token emitted by the latest preview:
  uv run python scripts/backfill_iitk_image_task_eligibility.py --project-id 5 \
    --apply --confirm-token IITK-TASKS-5-...
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
from iitk_api_integration.task_eligibility import (
    IITKTaskEligibilityError,
    apply_iitk_task_eligibility,
    preview_iitk_task_eligibility,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-token")
    args = parser.parse_args()
    if args.apply and not args.confirm_token:
        parser.error("--apply requires --confirm-token from a fresh preview")
    if not args.apply and args.confirm_token:
        parser.error("--confirm-token is only valid with --apply")

    try:
        with transaction_scope() as db:
            if args.apply:
                result = apply_iitk_task_eligibility(
                    db,
                    project_id=args.project_id,
                    confirmation_token=args.confirm_token,
                )
                mode = "applied"
            else:
                result = preview_iitk_task_eligibility(db, project_id=args.project_id)
                mode = "preview"
            print(json.dumps({"mode": mode, **result.to_dict()}, indent=2, sort_keys=True))
    except IITKTaskEligibilityError as exc:
        print(json.dumps({"mode": "error", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
