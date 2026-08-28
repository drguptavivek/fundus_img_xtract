# Authz v2 slice 48: Remidio ZIP upload

- [x] G1 Form admission and upload mutation are explicitly distinct.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_remidio_zip_upload_separates_workspace_and_exact_upload_target -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes with screen form and exact mutation contracts.

- [x] G2 Upload mutation denies without its exact project-site target.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_every_exact_action_denies_when_the_route_omits_its_resource -q'
  EXPECT: exit 0
  EVIDENCE: All exact-action missing-resource cases pass in the 186-test run.

- [x] G3 ZIP and ingest validation stays outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no file, mode, or camera facts were added.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory passes at 590 explicit and 51 unmapped routes; slice 48 is documented.
