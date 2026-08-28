# Authz v2 slice 23: remove grading workflow domain leakage

- [x] G1 Grading authorization evaluates only durable authorization relationships, not task workflow state or prior-grade business rules.
  CHECK: ! rg -n "workflow_accepts|no_conflict|no_duplicate|_ACCEPTED_STATE" authz_v2
  EXPECT: exit 0
  EVIDENCE: banned markers are absent and a foundation boundary regression test enforces this

- [x] G2 Exact grading allocation and disease/lab/slot authorization remain fail closed and covered.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_relationship_providers.py tests/unit/authz_v2/core/test_contracts.py tests/unit/authz_v2/test_domain_scenarios.py -q
  EXPECT: exit 0
  EVIDENCE: focused contract, provider, and scenario suite passes 1007 tests

- [x] G3 The Authz v2 test suite passes.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2 -q
  EXPECT: exit 0
  EVIDENCE: Authz v2 suite passes 1103 tests with 3 warnings

- [x] G4 Documentation records the authorization/domain boundary.
  CHECK: rg -n "workflow state.*application service|prior-grade.*application service" docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: slice 23 records workflow state, duplicates, and prior-grade conflict as application-service rules
