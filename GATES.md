# Gates: Authorization v2 vertical slice 1 - clinical media

Scope: Begin the 677-consumer migration with the complete 17-route clinical media family, establish dynamic exact-action bindings needed by later slices, and leave the remaining 660 consumers explicitly visible and fail-closed for future slices.

- [x] G1: All 17 production media routes have explicit canonical action, mode, exact resolver or closed dynamic binding, and central enforcement metadata.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: /3 passed/
  EVIDENCE: Inventory reports authz_v2=17, legacy_unmapped=613, automation_unmapped=47; media-family test requires exactly 17/17 authz_v2 rows.

- [x] G2: Signed media actions require exact resource, active target, signed channel, and stored signed-credential relationship; omission of any selected fact denies.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/core/test_contracts.py -q
  EXPECT: /passed/
  EVIDENCE: Core exhaustive path-removal suite passed as part of the 720-test combined run.

- [x] G3: The polymorphic signed media route may select only its declared image/PDF actions, and missing/invalid binding or resource denies before handler execution.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_endpoint_enforcement.py tests/unit/authz_v2/test_flask_guard.py -q
  EXPECT: /12 passed/
  EVIDENCE: 12 endpoint contract/enforcement tests passed in the focused run; undeclared dynamic action leaves service uncalled.

- [x] G4: Generated executable-policy artifacts and deterministic consumer baseline match the new catalogue and route contracts exactly.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: /5 passed/
  EVIDENCE: 5 passed after regeneration; fingerprint 6851094b619dd3800bdc2421d681f0b9dc97cc2c5d83ce11a047f8125680aba3.

- [x] G5: Authz v2 remains inactive, the single-migration/clean-cutover boundary remains intact, and the remaining 660 runtime consumers remain explicitly counted rather than inferred as authorized.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_foundation_boundary.py tests/unit/authz_v2/test_migration.py -q
  EXPECT: /4 passed/
  EVIDENCE: Boundary and migration tests passed in the 720-test combined run; inventory documents 613 HTTP plus 47 worker gaps.

- [ ] G6: Static checks, direct adversarial review, Beads export, scoped commit, pull/rebase, and push succeed while unrelated user files remain untouched.
  CHECK: git diff --check
  EXPECT: clean
  EVIDENCE: pending
