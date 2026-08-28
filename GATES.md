# Authz v2 slice 34: WAI statistics API

- [x] G1 All five WAI statistics routes have explicit Authz v2 contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_wai_statistics_routes_separate_admission_rows_and_retry -q'
  EXPECT: exit 0
  EVIDENCE: Focused family test passes; all five routes classify as Authz v2.

- [x] G2 Statistics reads are screen admission while retry resolves the exact persisted inference run.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_legacy_manifest_maps_every_action_exactly_once tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_wai_statistics_routes_separate_admission_rows_and_retry -q'
  EXPECT: exit 0
  EVIDENCE: Four reads are screen mode without a resolver; retry uses inference.wai.run.retry with inference_result.

- [x] G3 Retry eligibility and statistics filters remain application-domain logic.
  CHECK: ! rg -n 'inference_status|result_type|capture_start|capture_end' authz_v2
  EXPECT: exit 0
  EVIDENCE: No inference status, result type, or capture-date filter predicates occur under authz_v2.

- [x] G4 Inventory, generated catalogue artifacts, and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Five contract/generated-doc/inventory tests pass; inventory is 527 explicit and 114 unmapped; catalogue is 220.
