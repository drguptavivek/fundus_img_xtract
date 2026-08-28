# Authz v2 slice 42: remaining analytics views

- [x] G1 Seven remaining analytics routes have explicit contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_remaining_analytics_views_separate_admission_and_exact_media -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; all seven routes classify as Authz v2.

- [x] G2 Direct-image and encounter views resolve exact persisted resources.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_remaining_analytics_views_separate_admission_and_exact_media -q'
  EXPECT: exit 0
  EVIDENCE: Direct view uses direct_image_upload and encounter view uses encounter.

- [x] G3 KPI/model/statistics routes are admission-only pending query policies.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_remaining_analytics_views_separate_admission_and_exact_media -q'
  EXPECT: exit 0
  EVIDENCE: Five analytical routes are screen mode without a resolver; plan records required SQL policy replacement.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory/family tests pass at 569 explicit and 72 unmapped routes; plan slice 42 records the boundary.
