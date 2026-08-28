# Authz v2 slice 61: EncounterSet identifier export

- [x] G1 EncounterSet export binds the exact requested project.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_encounter_set_identifier_export_binds_the_exact_project -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run.

- [x] G2 Identifier release requires ordinary scoped authority plus PII_EXPORTER.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passed in the combined Docker run.

- [x] G3 Export filters and workbook content remain outside Authz v2.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: All domain-boundary tests passed in the combined Docker run.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Main Docker selection passed 1166 of 1167 tests; the sole failure exposed that the new action was initially placed in the legacy-name manifest. It was moved to the canonical-only manifest and the failed contract then passed. Inventory is 633 authz_v2 and 8 legacy_unmapped routes.
