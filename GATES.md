# Authz v2 slice 29: upload metadata field definitions

- [x] G1 All six upload-metadata definition endpoints have explicit contracts.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: Consumer inventory and family-specific tests passed; inventory reports 503 explicit Authz v2 routes and 138 remaining unmapped routes.

- [x] G2 Creation uses an exact named system operation; updates use an exact persisted definition.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: Family-specific contract test passed for create on upload_metadata_field_definition_create and three mutations on upload_metadata_field_definition.

- [x] G3 Definition content validation remains outside Authz v2.
  CHECK: ! rg -n "selection_mode|validation_regex|required_at_upload|is_pii_default" authz_v2
  EXPECT: exit 0
  EVIDENCE: Repository search returned no selection_mode, validation_regex, required_at_upload, or is_pii_default policy facts under authz_v2.

- [x] G4 Inventory, catalogue artifacts, and documentation are current.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web uv run pytest tests/unit/authz_v2/test_generated_policy_docs.py tests/unit/app_init/test_authz_v2_consumer_inventory.py -q
  EXPECT: exit 0
  EVIDENCE: Six focused contract, adapter, generated-doc, and inventory tests passed; catalogue count is 212 and inventory fingerprint is 7b20c17015c3392a17b3873713e809d1139b8e331109cd887fef465e43caad73.
