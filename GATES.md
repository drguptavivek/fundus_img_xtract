# Authz v2 slice 26: intra-rater routes

- [x] G1 All eight intra-rater HTTP endpoints have explicit contracts.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: inventory family test confirms all eight classify Authz v2

- [x] G2 Batch creation requires an explicit valid lab-unit target and denies missing facts.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_resource_adapters.py tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: adapter rejects raw, zero, and unresolved targets; focused regression passes

- [x] G3 Viewer and submit routes require exact image and intra-rater-task resources.
  CHECK: rg -n "intra_rater_viewer|submit_intra_rater_grade" authz_v2/flask/route_catalogue.py tests/unit/app_init/test_authz_v2_consumer_inventory.py
  EXPECT: exit 0
  EVIDENCE: inventory regression asserts exact image viewer and intra-rater task submit resolvers

- [x] G4 Inventory, generated policy artifacts, and documentation are current.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: focused artifact/inventory suite passed; combined suite reached 1156 passes before one corrected manifest-count assertion, then all four affected regressions passed
