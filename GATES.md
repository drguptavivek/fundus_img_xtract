# Authz v2 slice 40: screenings routes

- [x] G1 All five screenings routes have explicit contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_screenings_routes_use_exact_encounters_for_reads_and_mutations -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; all five routes classify as Authz v2.

- [x] G2 Detail, reprocess, and deletion operations resolve the exact encounter.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_legacy_manifest_maps_every_action_exactly_once tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_screenings_routes_use_exact_encounters_for_reads_and_mutations -q'
  EXPECT: exit 0
  EVIDENCE: Four resource routes use their distinct view/reprocess/delete action with the encounter resolver.

- [x] G3 Task-state, report, file, and OCR eligibility remain application logic.
  CHECK: ! rg -n 'non_pending_tasks|ocr_processed|reports_exist|pending_tasks' authz_v2
  EXPECT: exit 0
  EVIDENCE: Authz source contains none of the screenings workflow variables used for eligibility.

- [x] G4 Inventory, generated policy artifacts, and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Five catalogue/generated-doc/inventory/family tests pass; inventory is 557 explicit and 84 unmapped; catalogue is 227.
