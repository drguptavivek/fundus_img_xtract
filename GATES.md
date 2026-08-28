# Authz v2 slice 32: viewer preferences API

- [x] G1 All five viewer settings and preset routes have explicit exact-self contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_viewer_preferences_api_is_exact_self_service -q'
  EXPECT: exit 0
  EVIDENCE: Viewer-family test passes; all five routes use account.viewer_preferences.manage with the exact user resolver.

- [x] G2 Viewer values, filters, ranges, and preset slots remain application validation.
  CHECK: ! rg -n 'loupe|brightness|contrast|slot_number|_VIEWER_FILTERS' authz_v2
  EXPECT: exit 0
  EVIDENCE: Source search finds no loupe, brightness, contrast, slot_number, or viewer-filter rules under authz_v2.

- [x] G3 Inventory baseline and fingerprint are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory test passes at 516 explicit routes, 125 unmapped routes, and fingerprint 613a96633e5f0b5aa4e515524f3745e2107c77a165f30f7c97c1e01b28176a3a.

- [x] G4 Documentation records the exact-self boundary and measured inventory.
  CHECK: rg -n 'viewer preferences API|exact self-service|516 v2 HTTP' docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: Plan slice 32 documents exact self-service and application-owned preference validation.
