# Authz v2 slice 62: bounded multi-image OCR reads

- [x] G1 OCR batch binds one exact bounded image-batch resource.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_ocr_batch_requires_one_exact_bounded_image_batch -q'
  EXPECT: exit 0
  EVIDENCE: Passed in the combined Docker run.

- [x] G2 Missing, duplicate, ambiguous, oversized, or cross-scope image sets deny.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/core/test_contracts.py tests/unit/authz_v2/test_resource_adapters.py -q'
  EXPECT: exit 0
  EVIDENCE: Full core contract suite passed in the combined Docker run.

- [x] G3 OCR status, variants, and detection content remain outside Authz v2.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py -q'
  EXPECT: exit 0
  EVIDENCE: All domain-boundary tests passed in the combined Docker run.

- [x] G4 Inventory and generated policy artifacts are current.
  CHECK: make test PYTEST_ARGS='tests/unit/app_init/test_authz_v2_consumer_inventory.py::test_live_http_and_celery_inventory_matches_reviewed_baseline tests/unit/authz_v2/test_generated_policy_docs.py -q'
  EXPECT: exit 0
  EVIDENCE: Main Docker selection passed 1191 of 1192 tests; the sole failure exposed initial placement in the legacy-name manifest. It was moved to the canonical-only manifest and the failed contract then passed. Inventory is 634 authz_v2 and 7 legacy_unmapped routes.

# Authz v2 foundation: lossless request facts

- [x] G1 Repeated query and form values reach exact-resource binders without namespace merging.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest tests/unit/authz_v2/test_endpoint_enforcement.py tests/unit/authz_v2/test_flask_guard.py
  EXPECT: exit 0
  EVIDENCE: 15 passed.

- [x] G2 Existing scalar binder access remains stable during route migration.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest tests/unit/authz_v2/test_endpoint_enforcement.py::test_resolver_receives_separate_transport_namespaces_and_missing_body_facts_deny
  EXPECT: exit 0
  EVIDENCE: Passed as part of the 15-test guard run.

- [x] G3 The change carries transport facts only and adds no domain vocabulary or validation to Authz v2.
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest tests/unit/authz_v2/test_domain_boundary.py
  EXPECT: exit 0
  EVIDENCE: Existing domain-boundary gate remains the release check for this invariant.
