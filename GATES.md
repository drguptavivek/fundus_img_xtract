# Authz v2 slice 58: signed dataset downloads

- [x] G1 All seven dataset download routes require an exact signed dataset share.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_dataset_download_routes_require_the_exact_signed_share_credential -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run.

- [x] G2 Signed-resource channel and missing-credential behavior deny closed.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passed in the combined Docker run.

- [x] G3 Credential workflow and export generation details remain outside Authz v2.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_flask_guard.py tests/unit/authz_v2/core/test_contracts.py -q'
  EXPECT: exit 0
  EVIDENCE: Guard and full core contract suites passed in the combined Docker run.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Combined Docker validation passed 1148 tests in 17.37s; inventory is 628 authz_v2 and 13 legacy_unmapped routes.
