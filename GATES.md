# Authz v2 slice 46: grader self-service dashboard

- [x] G1 All four grader dashboard APIs require the exact current user.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_grading_dashboard_family_uses_exact_self_authorization -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes for all four APIs with user resolvers.

- [x] G2 The new action enforces self without admin substitution.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passes within the 1106-test combined run.

- [x] G3 Clinical and workflow filters stay outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no disease or queue state facts were added.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined run passes 1106 tests at 583 explicit/58 unmapped; generated artifacts match.
