# Authz v2 slice 45: public analytics surface

- [x] G1 All three intended public analytics routes are explicit.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_public_analytics_family_is_explicitly_public -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes for the page and both aggregate APIs.

- [x] G2 Public classification uses only the dedicated public action.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_public_analytics_family_is_explicitly_public -q'
  EXPECT: exit 0
  EVIDENCE: Family test asserts PUBLIC mode and public.analytics.view for every route.

- [x] G3 Analytics calculations and disclosed content remain outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no analytics facts entered Authz.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory test passes at 579 explicit and 62 unmapped routes; slice 45 is documented.
