# Authz v2 slice 35: Remidio encounter migration API

- [x] G1 All five encounter-migration routes have explicit contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_remidio_encounter_migration_routes_are_exact -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; all five routes classify as Authz v2.

- [x] G2 Preview/apply require source project, target project, and the complete bounded encounter set.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_resource_adapters.py tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_remidio_encounter_migration_routes_are_exact -q'
  EXPECT: exit 0
  EVIDENCE: Adapter/route tests pass for invalid, same-project, and empty targets; resolver source inspection verifies duplicate/oversized rejection, complete loading, active projects, and source-project ownership.

- [x] G3 Capture-date and confirmation-token semantics remain application logic.
  CHECK: ! rg -n 'capture_date|confirmation_token' authz_v2
  EXPECT: exit 0
  EVIDENCE: Source search finds neither capture_date nor confirmation_token under authz_v2.

- [x] G4 Inventory, generated catalogue artifacts, and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Seven catalogue/adapter/doc/inventory tests plus two rerun inventory/family tests pass; inventory is 532 explicit and 109 unmapped; catalogue is 223.
