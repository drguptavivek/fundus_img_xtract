# Authz v2 slice 52: review options and AI model list

- [x] G1 Both list endpoints have explicit, appropriately narrow admission.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_discrepancy_options_and_ai_model_list_have_explicit_admission -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes with review-list and admin-only AI-model actions.

- [x] G2 AI-model admission remains admin-only.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passes within the 1120-test combined run.

- [x] G3 List content and filters stay outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no model/filter content facts were added.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined run passes 1120 tests at 600 explicit/41 unmapped; generated artifacts match.
