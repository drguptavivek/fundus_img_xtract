# Authz v2 slice 41: report and encounter viewers

- [x] G1 All five report/viewer routes have explicit contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_report_and_encounter_viewers_use_exact_resources -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; all five routes classify as Authz v2.

- [x] G2 PDF, encounter, and image delivery use exact typed resources.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_legacy_manifest_maps_every_action_exactly_once tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_report_and_encounter_viewers_use_exact_resources -q'
  EXPECT: exit 0
  EVIDENCE: PDF routes use report, encounter viewer uses encounter, and image viewer uses image resolvers.

- [x] G3 Presentation and selected-image validation remain application logic.
  CHECK: ! rg -n 'invalid_presentation|selected_image_not_found|autolaunch' authz_v2
  EXPECT: exit 0
  EVIDENCE: Authz source contains none of the viewer presentation or selected-image validation terms.

- [x] G4 Inventory, generated policy artifacts, and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Five catalogue/generated-doc/inventory/family tests pass; inventory is 562 explicit and 79 unmapped; catalogue is 229.
