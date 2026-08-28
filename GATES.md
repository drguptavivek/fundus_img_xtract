# Authz v2 slice 60: user notification relationships

- [x] G1 Compose and mark-read routes use exact dynamic recipient resources.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_user_notification_mutations_require_exact_recipient_relationships -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run.

- [x] G2 Peer and notification-recipient paths deny without persisted relationships.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py tests/unit/authz_v2/test_resource_adapters.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passed in the combined Docker run.

- [x] G3 Notification content and delivery behavior remain outside Authz v2.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: All domain-boundary tests passed in the combined Docker run.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Main Docker selection passed 1180 of 1182 tests; both failures were reviewed baselines introduced by the new adapter and line fingerprint. After registering the required legacy notification-target adapter and updating the fingerprint, both failed tests passed. Inventory is 632 authz_v2 and 9 legacy_unmapped routes.
