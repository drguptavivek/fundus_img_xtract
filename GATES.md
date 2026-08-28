# Gates: Authorization v2 vertical slice 3 - encounter verification

Scope: Migrate all 30 encounter-set and Remidio verification routes from the unmapped baseline, separating read permission from mutation authority and retaining exact encounter/image resource binding.

- [x] G1: All 16 encounter-set and 14 Remidio verification routes have explicit endpoint contracts and none remains unmapped.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: /6 passed/
  EVIDENCE: Inventory reports authz_v2=77 and legacy_unmapped=556; family test requires 30/30 verification routes classified.

- [x] G2: Read-only encounter-set routes use a distinct verification.encounter_set.view action; mutation routes require update or exact image-processing authority.
  EVIDENCE: Catalogue defines separate encounter-set view/update actions and route_catalogue maps each GET/mutation explicitly.

- [x] G3: Full Authz/app-init tests, generated policy parity, Ruff, Bandit, diff checks, direct adversarial review, Beads export, scoped commit, pull/rebase, and push succeed.
  CHECK: git diff --check && echo clean
  EXPECT: clean
  EVIDENCE: 728 tests passed; generated artefacts match; Ruff, Bandit, and diff checks passed; review confirmed body-only identifiers fail closed; Beads exported. Commit/push recorded in Git history.
