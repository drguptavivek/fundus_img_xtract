# Authz v2 slice 57: scoped context and AI execution

- [x] G1 Four context and AI routes bind exact user, task, or configuration resources.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_scoping_and_ai_integration_routes_bind_exact_authorization_targets -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run.

- [x] G2 Interactive inference is distinct from automation-channel inference and missing resources deny.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passed in the combined Docker run.

- [x] G3 Provider behavior, inference force/reuse, and operation-name semantics remain outside Authz v2.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: All 3 domain-boundary tests passed in the combined Docker run.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined Docker validation passed 1163 of 1164 tests; the sole failure was the intentionally changed identity fingerprint. The updated fingerprint baseline then passed independently. Inventory is 621 authz_v2 and 20 legacy_unmapped routes.
