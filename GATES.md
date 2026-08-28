# Authz v2 slice 44: project annotation policy administration

- [x] G1 Three policy endpoints use exact project authorization.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_project_annotation_policy_routes_use_exact_admin_project_actions -q'
  EXPECT: exit 0
  EVIDENCE: Focused family test passes for all three routes and project resolvers.

- [x] G2 The three new actions remain admin-only and resource exact.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full 1097-case core contract parametrization passes within the combined run.

- [x] G3 Domain annotation rules remain outside Authz v2.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; policy structure and format remain app code.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined run passes 1101 tests; inventory is 576 explicit/65 unmapped and generated artifacts match.
