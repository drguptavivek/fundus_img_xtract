# Authz v2 slice 38: help and self-scoped utility reads

- [x] G1 Help routes are explicitly public and utility reads are explicitly protected.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_help_upload_stats_and_eligible_lab_routes_are_explicit -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes for all seven URL rules across six endpoints.

- [x] G2 Eligible Lab Unit APIs authorize the exact current user.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_help_upload_stats_and_eligible_lab_routes_are_explicit -q'
  EXPECT: exit 0
  EVIDENCE: Both APIs use authorization.me.upload_options.view with the exact user resolver.

- [x] G3 Upload-stat admission is distinct from row-scoped SQL.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_help_upload_stats_and_eligible_lab_routes_are_explicit -q'
  EXPECT: exit 0
  EVIDENCE: Both statistics endpoints are screen mode without a resolver; plan records pending query-policy work.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory/family tests pass at 549 explicit and 92 unmapped routes; plan slice 38 records the classifications.
