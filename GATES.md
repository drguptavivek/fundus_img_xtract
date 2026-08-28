# Authz v2 slice 28: job routes

- [x] G1 All six browser job endpoints have explicit contracts.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: complete jobs/routes.py family classifies Authz v2

- [x] G2 Job status, result, and processing reads require an exact job token/id.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: four result/status policies assert jobs.result.view with job resolver

- [x] G3 Regeneration requires the exact job mutation action; list admission cannot authorize it.
  CHECK: rg -n "regenerate_export|Action.JOBS_REGENERATE" authz_v2/flask/route_catalogue.py tests/unit/app_init/test_authz_v2_consumer_inventory.py
  EXPECT: exit 0
  EVIDENCE: regeneration policy asserts jobs.regenerate with exact job resolver

- [x] G4 Inventory and documentation are current.
  CHECK: rg -n "497 v2 HTTP consumers.*144 unmapped HTTP" docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: inventory baseline and job family regressions pass; counts are 497 v2 and 144 unmapped HTTP
