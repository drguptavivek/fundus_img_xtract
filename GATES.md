# Authz v2 slice 37: project Lab Unit configuration API

- [x] G1 Both project Lab Unit configuration routes resolve the exact project.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_project_lab_unit_configuration_is_project_exact -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; both routes are Authz v2 and use the project resolver.

- [x] G2 Read and mutation use distinct project actions.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_project_lab_unit_configuration_is_project_exact -q'
  EXPECT: exit 0
  EVIDENCE: GET uses project.view; POST/PUT uses project.access.manage.

- [x] G3 Lab Unit selection and replacement validation remain application logic.
  CHECK: ! rg -n 'lab_unit_ids must be a list|replace_project_lab_units' authz_v2
  EXPECT: exit 0
  EVIDENCE: Authz source contains neither the payload validation message nor the replacement service call.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory/family tests pass at 542 explicit and 99 unmapped routes; plan slice 37 records the boundary.
