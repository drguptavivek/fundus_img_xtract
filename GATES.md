# Authz v2 slice 39: scoped hospital dashboard

- [x] G1 All three dashboard routes have explicit contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_legacy_dashboard_separates_admission_from_exact_hospital -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; all three dashboard routes classify as Authz v2.

- [x] G2 Hospital detail resolves a typed persisted hospital.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_legacy_manifest_maps_every_action_exactly_once tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_legacy_dashboard_separates_admission_from_exact_hospital -q'
  EXPECT: exit 0
  EVIDENCE: Hospital detail uses dashboard.hospital.view with the existing typed lookup_record resource contract; catalogue contract test passes.

- [x] G3 Dashboard list admission remains distinct from SQL row scoping.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_legacy_dashboard_separates_admission_from_exact_hospital -q'
  EXPECT: exit 0
  EVIDENCE: Landing and image list are screen mode without a resolver; plan records pending query-policy replacement.

- [x] G4 Inventory, generated policy artifacts, and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Five catalogue/generated-doc/inventory/family tests pass; inventory is 552 explicit and 89 unmapped; catalogue is 226.
