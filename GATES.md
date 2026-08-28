# Authz v2 slice 54: disease and EncounterSet lists

- [x] G1 Both list endpoints have explicit admission.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_disease_catalogue_and_unverified_encounter_list_have_explicit_admission -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes for both list endpoints.

- [x] G2 The identifier-bearing EncounterSet list uses PII-aware admission.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_disease_catalogue_and_unverified_encounter_list_have_explicit_admission -q'
  EXPECT: exit 0
  EVIDENCE: Family test asserts project.encountersets.workspace.view_pii.

- [x] G3 Disease and verification workflow data stays outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no disease or verification state was added.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory passes at 606 explicit and 35 unmapped routes; slice 54 is documented.
