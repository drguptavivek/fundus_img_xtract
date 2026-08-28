# Authz v2 slice 31: core domain-boundary hardening

- [x] G1 Authz adapters do not decide S3 retry status, grading-repair workflow state, or dataset-finalization lifecycle.
  CHECK: ! rg -n 'sync\.status|task\.state|dataset\.is_finalized' authz_v2
  EXPECT: exit 0
  EVIDENCE: Source sweep finds none of sync.status, task.state, or dataset.is_finalized under authz_v2; owning application routes/services retain these checks.

- [x] G2 Exact resource identity, scope, ownership, credentials, delegation, disclosure, and authorization-policy flags remain fail-closed.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2 -q'
  EXPECT: exit 0
  EVIDENCE: Complete Authz v2 unit suite passed: 1155 tests, 3 warnings.

- [x] G3 A regression test explicitly enforces the domain boundary.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: Two new boundary tests pass and prohibit workflow/content tokens plus unexpected domain_valid producer modules.

- [x] G4 Boundary behavior and rationale are documented without moving application validation into Authz.
  CHECK: rg -n 'Domain boundary|application services|authorization facts' docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: Plan slice 31 enumerates allowed authorization facts and application-owned S3, grading, dataset, clinical metadata, and upload-field rules.
