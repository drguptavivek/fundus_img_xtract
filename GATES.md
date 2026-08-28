# Authz v2 slice 47: image anonymization workspace

- [x] G1 The dashboard, three exact image routes, and static endpoint are explicit.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_preprocess_family_separates_workspace_exact_images_and_static_assets -q'
  EXPECT: exit 0
  EVIDENCE: Family test passes for all five endpoints and their distinct modes.

- [x] G2 Image mutations cannot authorize without an exact image resource.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py::test_every_exact_action_denies_when_the_route_omits_its_resource -q'
  EXPECT: exit 0
  EVIDENCE: All 182 exact-action missing-resource cases pass within the combined run.

- [x] G3 PII and image workflow logic stays outside Authz.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Both domain-boundary tests pass; no PII or image workflow facts were added.

- [x] G4 Inventory and documentation are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline -q'
  EXPECT: exit 0
  EVIDENCE: Inventory passes at 588 explicit and 53 unmapped routes; slice 47 is documented.
