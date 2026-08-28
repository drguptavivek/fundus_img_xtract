# Authz v2 slice 49: discrepancy task review

- [x] G1 GET and POST use distinct exact grading-task actions.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_review_task_detail_uses_exact_method_specific_task_actions -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes with exact GET view and POST submit contracts.

- [x] G2 Both decisions deny when the exact task is absent.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_every_exact_action_denies_when_the_route_omits_its_resource -q'
  EXPECT: exit 0
  EVIDENCE: All exact-action missing-resource cases pass in the 186-test run.

- [x] G3 Review workflow and clinical submission logic stays outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no review workflow facts were added.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory passes at 591 explicit and 50 unmapped routes; slice 49 is documented.
