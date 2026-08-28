# Authz v2 slice 33: hospital analytics dashboard

- [x] G1 All six hospital-dashboard routes have explicit screen-admission contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_hospital_dashboard_routes_are_screen_admission_only -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; all six page/JSON routes classify as Authz v2.

- [x] G2 Screen admission is not represented as row authorization.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_hospital_dashboard_routes_are_screen_admission_only -q'
  EXPECT: exit 0
  EVIDENCE: Family test confirms EndpointMode.SCREEN with no exact-resource resolver for all six routes.

- [x] G3 Inventory baseline and fingerprint are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory passes at 522 explicit routes, 119 unmapped routes, and fingerprint 613a96633e5f0b5aa4e515524f3745e2107c77a165f30f7c97c1e01b28176a3a.

- [x] G4 Documentation records separate query-policy work.
  CHECK: rg -n 'hospital analytics dashboard|does not authorize returned rows' docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: Plan slice 33 explicitly states screen admission does not authorize rows and records the pending SQL query-policy migration.
