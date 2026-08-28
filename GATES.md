# Authz v2 slice 27: KPI API admission

- [x] G1 All 12 encounter/direct-file KPI endpoints have explicit contracts.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: inventory family regression covers all 12; suite passes 45 tests

- [x] G2 Endpoint admission uses aggregate KPI authority and cannot authorize returned rows.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: every family policy is SCREEN with analytics.kpi.view and screen_entry

- [x] G3 Row/export queries retain row-level project gating pending registered SQL-policy migration.
  CHECK: rg -n "analytics.kpi.encounter_files.rows|project_gated=True" api/kpis/encounter_files_kpis.py api/kpis/direct_files_kpis.py
  EXPECT: exit 0
  EVIDENCE: encounter builders pass their row action and direct row/export callers enable project_gated; both remain query-policy work

- [x] G4 Inventory and documentation are current.
  CHECK: rg -n "491 v2 HTTP consumers.*150 unmapped HTTP" docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md
  EXPECT: exit 0
  EVIDENCE: generated inventory is 491 v2, 39 legacy literals, and 150 unmapped HTTP
