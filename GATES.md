# Gates: Authorization v2 live-consumer inventory and query policies

Scope: Complete cutover steps 1 and 2: exhaustively inventory live Flask/API/Celery authorization consumers and list queries, then implement the concrete action-specific SQL policies required by those live relationship/state-dependent lists. Keep `authz_v2` inactive and retain the single consolidated migration.

- [x] G1: A reproducible inventory enumerates every registered Flask/API endpoint and Celery task with source identity, any directly discoverable canonical action, and an explicit legacy/automation gap classification rather than inferred authorization.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: 680 HTTP rows and 47 Celery rows with the reviewed fingerprint

- [x] G2: Every production list-materialization site is present as an explicit review candidate, and each proven relationship/state-dependent live set is classified as action-specific, choice-only, or exact-only; none silently uses generic scope SQL.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run python -m scripts.authz_v2_inventory 2>/dev/null | jq -e '.counts.query_candidate_unmapped == 977 and ([.consumers[] | select(.kind == "query")] | length == 977)'
  EXPECT: true

- [x] G3: Each relationship/state-dependent live list has a registered `(action, resource_type)` SQL policy that reproduces the exact authorization rule before materialization, or an explicit fail-closed exact-only/choice-only classification.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_query_policies.py -q
  EXPECT: all pass

- [x] G4: Query-policy tests prove exact/list equivalence and deny missing facts, forged lineage, inactive ancestry, cross-project, cross-site, and classical-scope access to project-owned resources.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_query_policies.py tests/unit/authz_v2/test_scope_resolution.py tests/unit/authz_v2/test_resource_adapters.py -q
  EXPECT: all pass

- [x] G5: Inventory and policy catalogue parity is machine-checked so a new or changed protected route/task/list fails CI until explicitly classified.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py tests/unit/authz_v2/test_registry_lifecycle.py -q
  EXPECT: all pass and zero drift

- [x] G6: Route business validation remains outside Authz; only authorization-relevant upload-profile identity/allowance facts enter policy decisions, and missing required caller facts deny.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_relationship_providers.py tests/unit/authz_v2/test_services.py -q
  EXPECT: all pass

- [x] G7: The implementation preserves clean-cutover boundaries: `authz_v2` remains inactive, there is no legacy fallback/dual decision path, the working DB stays pre-authz, and exactly one authz_v2 migration exists.
  CHECK: inactive-boundary and migration invariant checks
  EXPECT: boundary_ok

- [x] G8: Full affected tests, Ruff, formatting, Bandit, diff checks, direct integration review, Beads export, commit, pull/rebase, and push succeed; origin equals HEAD and unrelated user changes remain untouched.
  CHECK: final combined validation and git verification
  EXPECT: all pass and branch up to date with origin
