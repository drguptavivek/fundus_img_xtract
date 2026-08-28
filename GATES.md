# Authz v2 slice 51: discrepancy review lists

- [x] G1 Queue pages and self history have explicit distinct contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_discrepancy_review_lists_separate_admission_and_self_history -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes for two screen actions and two exact self routes.

- [x] G2 Self history denies admin substitution and missing users.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passes within the 1117-test combined run.

- [x] G3 Queue filters and review workflow stay outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no queue or filter state was added.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined run passes 1117 tests at 598 explicit/43 unmapped; generated artifacts match.
