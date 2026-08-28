# Authz v2 slice 30: IITK integration API

- [x] G1 All eight IITK API routes have explicit Authz v2 contracts.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: Inventory and IITK family tests pass; all eight endpoints classify as authz_v2 and the inventory reports 511 explicit routes, 130 unmapped.

- [x] G2 Persisted configuration operations resolve the exact configuration, and project operations resolve the exact project.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_resource_adapters.py tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: Catalogue/adapter registration and route-family tests pass; project reads/writes use project and persisted browse/update/sync operations use iitk_configuration.

- [x] G3 New configuration authorization requires both project and Lab Unit identity; integration payload semantics stay outside Authz v2.
  CHECK: ! rg -n "base_url|api_token|page_size|timeout_seconds|verify_ssl|source_site_code" authz_v2
  EXPECT: exit 0
  EVIDENCE: IITKConfigurationTargetRef requires positive project_id and lab_unit_id and resolve_scope verifies their active relationship; search finds no remote connection or sync payload fields under authz_v2.

- [x] G4 Inventory, catalogue artifacts, and documentation are current.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/core/test_contracts.py::test_legacy_manifest_maps_every_action_exactly_once tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: Four generated-doc/inventory tests and five focused contract/adapter/inventory tests pass; catalogue count is 219 and fingerprint is a714b78fc04b6015af199ce06d8a751d2a17350ef5dc6cdf51bc59d30f46055b.
