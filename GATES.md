# Authz v2 slice 36: project review workspaces

- [x] G1 All eight project-review page and API routes have explicit contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_project_review_routes_are_project_exact -q'
  EXPECT: exit 0
  EVIDENCE: Focused family test passes; all eight routes classify as Authz v2.

- [x] G2 Project-specific summary/upload/grading reads resolve the exact project.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_legacy_manifest_maps_every_action_exactly_once tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_project_review_routes_are_project_exact -q'
  EXPECT: exit 0
  EVIDENCE: Six project-specific HTML/API reads use project.review.view with the exact project resolver.

- [x] G3 Project-list admission is distinct from SQL-scoped returned projects.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_project_review_routes_are_project_exact -q'
  EXPECT: exit 0
  EVIDENCE: Both list routes are screen mode without a resolver; documentation preserves separate SQL-projection work.

- [x] G4 Inventory, generated catalogue artifacts, and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Five catalogue/generated-doc/inventory/family tests pass; inventory is 540 explicit and 101 unmapped; catalogue is 225.
