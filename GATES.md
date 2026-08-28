# Authz v2 slice 53: ad-hoc task reads

- [x] G1 List admission and exact batch detail are distinct.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_ad_hoc_task_reads_separate_list_admission_and_exact_batch -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes for three list routes and exact batch detail.

- [x] G2 Batch detail denies without its exact resource.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_every_exact_action_denies_when_the_route_omits_its_resource -q'
  EXPECT: exit 0
  EVIDENCE: All exact-action missing-resource cases pass in the 189-test run.

- [x] G3 Search, disease, suitability, and creation rules stay outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no search or task workflow facts were added.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined run passes 189 tests at 604 explicit/37 unmapped; generated artifacts match.
