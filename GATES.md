# Authz v2 slice 55: EncounterSet exact resources

- [x] G1 Five routes bind their exact project, encounter, or image targets.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_encounter_set_resource_routes_use_exact_project_encounter_and_image_targets -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run; the exact-route family test succeeded.

- [x] G2 Exact actions deny missing resources and refresh is audited.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run; the full Authz v2 core contract suite succeeded.

- [x] G3 Encounter and refresh workflow stays outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run; both domain-boundary tests succeeded.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined Docker validation passed 1128 tests in 19.40s; inventory is 611 authz_v2 and 30 legacy_unmapped routes, and generated policy artifacts match source.
