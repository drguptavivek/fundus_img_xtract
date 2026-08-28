# Authz v2 slice 25: Remidio verification routes

- [x] G1 All DR, glaucoma, and no-DR verification routes have explicit method-specific contracts.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: complete 19-endpoint family is classified Authz v2; inventory suite passes 43 tests

- [x] G2 Exact reads and mutations require encounter facts; list/result pages are screen admission only.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: method-specific assertions cover all three edit routes and exact update actions

- [x] G3 Glaucoma cleaning POST is an exact administrative operation, not screen admission.
  CHECK: rg -n 'glaucoma_clean_workflow.*"POST"|Action.ADMIN_SYSTEM_OPERATION' authz_v2/flask/route_catalogue.py tests/unit/app_init/test_authz_v2_consumer_inventory.py
  EXPECT: exit 0
  EVIDENCE: regression test asserts GET screen and POST exact system_operation resolver

- [x] G4 Inventory counts and documentation are updated.
  CHECK: rg -n "471 v2 HTTP consumers.*168 unmapped HTTP" docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: generated inventory is 471 v2 HTTP and 168 unmapped HTTP with fingerprint bd47c535
