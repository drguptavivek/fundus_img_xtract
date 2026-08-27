# Gates: Authorization v2 vertical slice 2 - grading and regrading

Scope: Migrate all 30 grading routes through an explicit endpoint catalogue, including all 27 routes from the 677-item unmapped baseline, while preserving action-specific SQL queue enforcement and fail-closed exact task/slot bindings.

- [x] G1: Every grading HTTP route is explicitly catalogued; none remains legacy-unmapped or action-literal-only.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: /4 passed/
  EVIDENCE: Inventory test requires 30/30 grading routes classified authz_v2; global counts are authz_v2=47, legacy_unmapped=586, automation_unmapped=47.

- [x] G2: Dashboard/queue/workbench contracts are screen admission only, while task, submit, feature, intra-rater, regrade, inference, and job routes bind action-specific exact resources.
  EVIDENCE: authz_v2/flask/route_catalogue.py explicitly lists every grading endpoint and its mode/action/resolver or closed binding.

- [x] G3: Resident, Resident2, and Arbitrator task routes use a closed three-action selector and relationship-aware queues remain SQL-scoped before materialization.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_endpoint_enforcement.py tests/unit/authz_v2/test_query_policies.py -q
  EXPECT: /14 passed/
  EVIDENCE: Dynamic selector allowlist and exact/list grading equivalence passed in the 26-test focused run.

- [x] G4: The endpoint catalogue is consumed identically by the live default-deny hook, unclassified-endpoint audit, manifest, and deterministic inventory.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_flask_guard.py tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: /12 passed/
  EVIDENCE: Focused contract/inventory suite passed; catalogue entries project through the same manifest used by inventory.

- [x] G5: Full affected Authz tests, Ruff, Bandit, diff checks, direct adversarial review, Beads export, scoped commit, pull/rebase, and push succeed while unrelated user files remain untouched.
  CHECK: git diff --check && echo clean
  EXPECT: clean
  EVIDENCE: 722 authz_v2/app_init tests passed; Ruff, Bandit, and diff checks passed; direct review added live-registration parity and preserved exact/list separation; Beads exported. Commit/push evidence recorded in Git history.
