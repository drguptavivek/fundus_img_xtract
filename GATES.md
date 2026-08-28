# Authz v2 slice 43: task, upload, and audit workspaces

- [x] G1 Four task/upload/audit workspaces have explicit admission.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_task_upload_and_audit_workspaces_are_explicit -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes; all four routes classify as Authz v2.

- [x] G2 Workspace admission is not represented as row authorization.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_task_upload_and_audit_workspaces_are_explicit -q'
  EXPECT: exit 0
  EVIDENCE: All four routes are screen mode without an exact-resource resolver.

- [x] G3 Existing application filters remain transitional pending SQL policies.
  CHECK: rg -n 'query-policy|SQL' docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: Plan explicitly records registered SQL query-policy replacement before cutover.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory/family tests pass at 573 explicit and 68 unmapped routes; plan slice 43 is current.
