# Gates: Authorization v2 core gap closure

Scope: Harden the inactive `authz_v2` foundation. Do not register it in the live Flask application, migrate production consumers, or apply the database migration to the working database.

- [x] G1: Signed-resource, mobile, and automation authorization use server-verified, principal-bound, unexpired credentials/sessions; password-reset credentials are constant-time verified and atomically single-use.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_verified_sessions.py tests/unit/authz_v2/test_relationship_providers.py -q
  EXPECT: /passed/
  EVIDENCE: targeted hardening suite: 48 passed in 7.21s

- [x] G2: Missing or invalid lineage never becomes implicit SYSTEM scope; active persisted ancestors are required, while legitimate system resources opt in explicitly.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_scope_resolution.py tests/unit/authz_v2/test_resource_adapters.py -q
  EXPECT: /passed/
  EVIDENCE: targeted hardening suite: 48 passed in 7.21s

- [x] G3: Authorization receipts retain typed scope and only the selected branch's non-secret relationship evidence, including upload profile, grading allocation, credential, and automation rule identities.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_receipts.py tests/unit/authz_v2/test_services.py -q
  EXPECT: /passed/
  EVIDENCE: targeted hardening suite: 48 passed in 7.21s

- [x] G4: Mandatory-audit and break-glass operations fail closed when durable audit recording fails; identifier releases are mandatory-audited; operational telemetry covers allow, deny, and internal error without changing decisions or exposing secrets.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_audit_enforcement.py tests/unit/authz_v2/test_telemetry.py -q
  EXPECT: /passed/
  EVIDENCE: targeted hardening suite: 48 passed in 7.21s

- [x] G5: SQL filtering invokes explicit action-and-resource query policies for registered relationship-aware reads and denies every unregistered non-scope-only query.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_query_policies.py tests/unit/authz_v2/test_services.py -q
  EXPECT: /passed/
  EVIDENCE: targeted hardening suite: 48 passed in 7.21s

- [x] G6: Protected endpoint classification centrally enforces the declared authorization decision with fail-closed resource resolution; signed, mobile, and automation endpoints cannot pass on caller claims or decoration alone.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_endpoint_enforcement.py tests/unit/authz_v2/test_foundation_boundary.py -q
  EXPECT: /passed/
  EVIDENCE: targeted hardening suite: 48 passed in 7.21s

- [x] G7: Core registries are composed once, reject conflicts, freeze before use, and remain deterministic under concurrent access.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_registry_lifecycle.py tests/unit/authz_v2/test_authorization_api.py -q
  EXPECT: /passed/
  EVIDENCE: targeted hardening suite: 48 passed in 7.21s

- [x] G8: All core tests, lint, formatting, security scan, migration invariant, and inactive-cutover boundary pass; the working database remains at the pre-authz revision and exactly one authz_v2 migration exists.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run --with ruff ruff check authz_v2 api/authorization.py tests/unit/authz_v2 migrations/versions/e735238d678b_add_unified_authorization_grants_and_.py && docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run --with ruff ruff format --check authz_v2 api/authorization.py tests/unit/authz_v2 migrations/versions/e735238d678b_add_unified_authorization_grants_and_.py && docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run --with bandit bandit -r authz_v2 api/authorization.py -q && git diff --check && docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2 tests/unit/app_init -q && test "$(rg --files migrations/versions | rg -c 'e735238d678b_add_unified_authorization_grants_and_\.py$')" -eq 1 && ! rg -l 'down_revision.*e735238d678b' migrations/versions --glob '*.py' && ! rg -n 'authz_v2|install_default_deny|api\.authorization' app.py api/__init__.py && test "$(docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run alembic current 2>/dev/null | tail -n 1)" = "0d3edcf7bc3b" && echo boundary_ok
  EXPECT: /boundary_ok/
  EVIDENCE: Ruff, format, Bandit, diff check passed; 704 tests passed in 9.33s; boundary_ok
