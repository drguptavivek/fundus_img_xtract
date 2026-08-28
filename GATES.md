# Authz v2 slice 59: administrator notification sends

- [x] G1 Notification form GET and mutation POST have separate authorization contracts.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_admin_notification_forms_separate_screen_entry_from_exact_send -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run.

- [x] G2 Each POST requires a closed exact system-operation reference.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_resource_adapters.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passed in the combined Docker run.

- [x] G3 Notification content and delivery behavior remain outside Authz v2.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: All domain-boundary tests passed in the combined Docker run.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Docker validation passed 25 tests in 14.16s; inventory is 630 authz_v2 and 11 legacy_unmapped routes.
