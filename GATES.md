# Authz v2 slice 24: separate dataset lifecycle from authorization

- [x] G1 Dataset lifecycle state is not evaluated by Authz v2.
  CHECK: ! rg -n "dataset_state_facts" authz_v2
  EXPECT: exit 0
  EVIDENCE: lifecycle provider is removed and the foundation boundary test bans its return

- [x] G2 Dataset project/site enablement remains an authorization policy and fails closed.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_relationship_providers.py tests/unit/authz_v2/test_resource_adapters.py tests/unit/authz_v2/core/test_contracts.py -q
  EXPECT: exit 0
  EVIDENCE: focused provider, adapter, and contract suite passes 1017 tests

- [x] G3 Generated policy artifacts and the Authz v2 suite pass.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2 -q
  EXPECT: exit 0
  EVIDENCE: Authz v2 suite passes 1103 tests with 3 warnings

- [x] G4 The cutover plan assigns lifecycle validation to the dataset application service.
  CHECK: rg -n "Dataset active/finalized lifecycle.*dataset application service" docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: slice 24 records lifecycle transitions as dataset-service responsibilities
