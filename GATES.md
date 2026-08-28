# Authz v2 slice 50: self context and bulk notifications

- [x] G1 All three routes bind the exact current user.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_self_context_and_bulk_notification_routes_use_exact_current_user -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes with user resolver and dedicated self actions.

- [x] G2 Self actions reject admin substitution and missing users.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full 1100-case core contract suite passes within the combined run.

- [x] G3 Notification filtering and read-state behavior stays outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; notification state was not modeled.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory passes at 594 explicit and 47 unmapped routes; slice 50 is documented.
