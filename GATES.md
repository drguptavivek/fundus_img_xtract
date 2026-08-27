# Gates: Authorization v2 foundation completion

Scope: Complete and verify the inactive `authz_v2` foundation without registering it in the live Flask application, migrating production consumers, or applying the database migration.

- [x] G1: The canonical role/action catalogue encodes every settled policy divergence that can be decided in the pure foundation, including verification, pregraded upload, dataset/export, grading, inference, public analytics, notification sending, allocation management, EXIF/PII, and delegation rules.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/core -q
  EXPECT: /passed/
  EVIDENCE: (7 durations < 0.005s hidden.  Use -vv to show these durations.) | [32m============================= [32m[1m615 passed[0m[32m in 9.38s[0m[32m ==============================[0m

- [x] G2: Every exact resource type declared by the catalogue has a registered authoritative resolver and SQL query scoper; forged lineage and exact/list disagreement fail tests.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_resource_adapters.py tests/unit/authz_v2/test_services.py -q
  EXPECT: /passed/
  EVIDENCE: (8 durations < 0.005s hidden.  Use -vv to show these durations.) | [32m============================== [32m[1m16 passed[0m[32m in 6.58s[0m[32m ==============================[0m

- [x] G3: Specialized upload-profile, grading-slot/allocation, participation, signed-credential, automation, site-policy, workflow-state, disclosure, and identifier-release facts have typed providers with independent positive and negative tests.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_relationship_providers.py tests/unit/authz_v2/test_domain_scenarios.py -q
  EXPECT: /passed/
  EVIDENCE: (8 durations < 0.005s hidden.  Use -vv to show these durations.) | [32m============================== [32m[1m14 passed[0m[32m in 6.20s[0m[32m ==============================[0m

- [x] G4: Exactly one consolidated ID-only authz_v2 migration contains complete idempotent upgrade/downgrade logic, rejects ambiguity or widening, emits non-PII conversion evidence, and passes migration tests without being applied to the working database.
  CHECK: test "$(rg --files migrations/versions | rg -c 'e735238d678b_add_unified_authorization_grants_and_\.py$')" -eq 1 && ! rg -l 'down_revision.*e735238d678b' migrations/versions --glob '*.py' && docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_migration.py -q
  EXPECT: /passed/
  EVIDENCE: (4 durations < 0.005s hidden.  Use -vv to show these durations.) | [32m============================== [32m[1m2 passed[0m[32m in 6.03s[0m[32m ===============================[0m

- [x] G5: Authorization catalogue/grant APIs and services are complete and tested but remain deliberately unregistered; no live Flask route or application initialization imports `authz_v2`.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_authorization_api.py tests/unit/authz_v2/test_foundation_boundary.py -q
  EXPECT: /passed/
  EVIDENCE: (8 durations < 0.005s hidden.  Use -vv to show these durations.) | [32m============================== [32m[1m4 passed[0m[32m in 7.50s[0m[32m ===============================[0m

- [x] G6: Generated Markdown, HTML, and matrix artifacts agree with the canonical role/action catalogue and document all foundation behavior without claiming live enforcement.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_generated_policy_docs.py -q
  EXPECT: /passed/
  EVIDENCE: (4 durations < 0.005s hidden.  Use -vv to show these durations.) | [32m============================== [32m[1m2 passed[0m[32m in 6.67s[0m[32m ===============================[0m

- [x] G7: The complete inactive foundation passes lint, formatting, unit/integration checks, security scan, and whitespace validation.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run --with ruff ruff check authz_v2 api/authorization.py app_init/logging_config.py db_base.py tests/unit/authz_v2 migrations/versions/e735238d678b_add_unified_authorization_grants_and_.py && docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run --with ruff ruff format --check authz_v2 api/authorization.py app_init/logging_config.py db_base.py tests/unit/authz_v2 migrations/versions/e735238d678b_add_unified_authorization_grants_and_.py && docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run --with bandit bandit -r authz_v2 api/authorization.py -q && git diff --check && docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2 tests/unit/app_init -q
  EXPECT: /passed/
  EVIDENCE: (6 durations < 0.005s hidden.  Use -vv to show these durations.) | [32m============================= [32m[1m688 passed[0m[32m in 9.51s[0m[32m ==============================[0m

- [x] G8: Scope boundary is preserved: the working database remains before the new migration, legacy engines remain untouched for the later atomic cutover, and `authz_v2` remains inactive in the live app.
  CHECK: test -d auth && test -d data_authorization && ! rg -n 'authz_v2|install_default_deny|api\.authorization' app.py api/__init__.py && test "$(docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run alembic current 2>/dev/null | tail -n 1)" = "0d3edcf7bc3b" && echo boundary_ok
  EXPECT: /boundary_ok/
  EVIDENCE: boundary_ok
