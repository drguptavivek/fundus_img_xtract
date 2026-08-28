# Gates: Authorization v2 vertical slice 4 - mobile clinical APIs

Scope: Migrate all 27 mobile API routes from the unmapped baseline with explicit credential-channel, self/session ownership, upload-profile, project/site lineage, and encounter/media binding.

- [x] G1: All 27 mobile API routes have explicit endpoint contracts and none remains unmapped.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: mobile family 27/27 classified and legacy_unmapped reduced by 27
  EVIDENCE: Inventory test requires 27/27 mobile routes classified; authz_v2=104 and legacy_unmapped=529.

- [x] G2: Login is the only public mobile route; refresh/logout/session management require the correct credential or mobile session and exact self/session ownership, with missing or mismatched facts denied.
  CHECK: targeted authz_v2 Flask/catalogue and mobile-session tests
  EXPECT: cross-user session access and incomplete credential facts deny
  EVIDENCE: Route contract and signed-credential tests cover public/signed/mobile separation, exact refresh hash/session binding, revocation, channel replay, and self-only session resources.

- [x] G3: Field project/encounter/image/report reads and inference requests enforce mobile channel plus exact project/site/encounter/media lineage; list routes scope before materialization.
  CHECK: targeted catalogue, decision, binding, and list-scope tests
  EXPECT: cross-project and cross-site cases deny; missing lineage denies
  EVIDENCE: Exact project/encounter route contracts require mobile channel and scoped clinical roles; PROJECT_PI/SITE_PI oversight alone is explicitly denied mobile field operation. Within-encounter image/report lineage remains application validation.

- [x] G4: Upload create/status/inference/thumbnail routes require exact upload owner/session/profile facts, and no route relies on a body-only identifier unavailable to the authorization hook.
  CHECK: targeted upload resource adapter and route-binding tests
  EXPECT: mismatched owner/profile/session and missing facts deny
  EVIDENCE: Create uses exact project-site/profile action; follow-up job actions require current scoped upload authority plus ownership. Resolver transport test proves separate path/query/form/JSON namespaces and missing form facts deny.

- [x] G5: Full Authz/app-init tests, generated policy parity, Ruff, Bandit, diff checks, direct adversarial review, Beads export, scoped commit, pull/rebase, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EXPECT: all gates checked with fresh evidence and no pending markers
  EVIDENCE: 795 tests passed; generated artifacts match; Ruff, Bandit, and diff checks passed. Direct adversarial review tightened upload ownership/current scope and denied oversight-only mobile operation. Beads, commit, rebase, and push are recorded in repository history.
