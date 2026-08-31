# Gates: full pytest suite stabilization (branch vg-work/full-suite-cleanup)

Scope: repair the 122 failed + 71 error results from the 2026-08-28 `make test`
baseline, in the handoff's dependency order, without weakening lean fail-closed
authorization. Baseline: 1,314 passed, 29 skipped, 13 xfailed, 1 xpassed.
No new skips/xfails without explicit user approval. Guardrails in
handoff/01_GUARDRAILS.md are binding for every gate below.

- [x] P1.1: shared user-fixture cluster green (unique-seed collisions, role assertions, partial app login_manager)
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/unit/test_user_fixtures.py tests/integration/auth/test_login_fixtures.py tests/unit/auth/test_site_admin_isolation.py > /tmp/gate_p11.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: 17 passed, 1 xfailed (pre-existing) in 9.30s

- [x] P1.2: auth roles db-session + runner/reauth/exports fixture-error families green
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/integration/auth/test_auth_roles_db_session.py tests/integration/common/test_runner.py tests/integration/common/test_runner_pytest.py tests/integration/security/test_reauth_decorator.py tests/integration/security/test_reauth_ui.py tests/integration/security/test_sensitive_exports.py tests/security/test_sensitive_operations_dashboard.py > /tmp/gate_p12.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: GATE_OK (44 passed; /admin 404 fixed to real route /admin/users)

- [x] P2.1: every remaining 403/404 failure classified (test | route | actor | supplied facts | required facts | policy | action) in handoff/03_FAILURE_INVENTORY.md or Beads
  EVIDENCE: all 403/404 families classified with recorded action: stale fixtures (missing ProjectRoleGrant → _grant_project_verify helper; missing ProjectLabUnit joins; legacy seed IDs modernized to 100/101), stale expectations (non-disclosing 404 family kept; viewer-shell pages assert isolation at the JSON API /api/encounter-viewer/*), stale test symbols (scope→clinical_rows, created_by_id, final_plus_review, status_override, /admin→/admin/users, hyphenated verify URLs). No product authorization semantics changed.

- [x] P2.2: lean-authz/security regression gate green
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/unit/authz tests/unit/data_authorization tests/security/test_authz_route_coverage.py tests/security/test_apply_scoping_site_admin.py tests/security/test_query_isolation.py > /tmp/gate_p22.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: GATE_OK (green before and after every phase; re-verified 2026-08-28).

- [x] P3.1: encounter editor/verify/CSRF/race/input-validation/hospital-scoping cluster green
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/integration/test_encounter_set_editor.py tests/integration/test_verify_encounter_set_routes.py tests/unit/api/test_encounter_set_csrf_protection.py tests/unit/api/test_encounter_set_race_conditions.py tests/unit/verify_encounter_set/test_input_validation.py tests/unit/verify_encounter_set/test_hospital_scoping.py tests/integration/test_encounter_set_celery.py > /tmp/gate_p31.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: 2026-08-28: all files green. test_upload_schedules_thumbnail_generation DELETED by user decision (endpoint removed; scheduler unwired in product). Celery generator fix: thumbnails now resolve under BASE_DIR/<folder_rel>/thumbnails matching the media-serving contract (was broken for every encounter-set image).

- [x] P3.2: mobile uploads/options/device-enrolment green; PWA-3 tests DEFERRED (ABANDON note below)
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/unit/api/test_mobile_uploads.py tests/unit/api/test_mobile_upload_options.py tests/unit/api/test_mobile_pwa.py tests/unit/mobile_devices/test_device_enrolment.py tests/integration/api/test_mobile_upload_contract.py > /tmp/gate_p32.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: 2026-08-28: uploads 9/9, options 6/6, devices 10/10, contract 1/1 (missing ProjectLabUnit join row + device approval in fixtures). PWA-3 tests DEFERRED this pass per user decision (Flutter PWA owns its own security layer; Python app not its authz boundary).

- [x] P3.3: analytics/security isolation/PII/screenings/dashboard cluster green
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/unit/security/test_analytics_isolation.py tests/unit/security/test_screenings_isolation.py tests/security/test_dashboard_authz.py tests/security/test_dashboard_isolation.py tests/security/test_pii_leakage.py tests/unit/analytics/test_analytics_pii.py tests/unit/analytics/test_analytics_utils.py tests/unit/utils/test_task_utils_pii.py tests/integration/analytics/test_kpis_api.py tests/integration/api/test_hospital_isolation_apis.py tests/unit/encounter_viewer/test_api.py tests/integration/api/test_project_review_api.py tests/unit/api/test_grading_dashboard_api.py > /tmp/gate_p33.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: 2026-08-28 all green incl. hospital_isolation_apis 8/8+1 xfail (fixtures modernized to seed IDs 100/101 per user decision; endpoint scoping verified correct: clinical_hospitals + viewer-shell/API split asserted at /api/encounter-viewer/*).

- [x] P3.4: thumbnails green with explicit aspect-ratio product decision (user approval if behavior changes)
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/integration/thumbnails/test_thumbnail_image_processing.py tests/unit/services/test_thumbnail.py > /tmp/gate_p34.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: user decision 2026-08-28: preserve aspect ratio. 26/26 pass. Also fixed latent GIF/palette JPEG-encode bug (utils/image_processing.py).
  ABANDON: PWA-3 tests (tests/unit/api/test_mobile_pwa.py) deferred by user decision: the Flutter PWA owns its own security layer and is out of scope for the Python authz cleanup pass.

- [x] P3.5: utilities cluster green (rate limiter, materialized views, filename validation, error sanitization, task backfill, anonymization workflow, PII task utils)
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/unit/utils/test_rate_limiter.py tests/unit/utils/test_materialized_view_scheduler.py tests/unit/utils/test_filename_validation.py tests/unit/utils/test_error_sanitization.py tests/unit/utils/test_task_backfill.py tests/unit/preprocess/test_anonymization_workflow.py tests/unit/utils/test_task_utils_pii.py > /tmp/gate_p35.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: 2026-08-28 green: rate limiter 42/42 (restored missing Limiter import - product fix; request-context guard; sys.path hack), MV scheduler (ai_inference_runs_mv added to expectation), filename validation 13/13 (product hardening: path separators rejected), error sanitization (runtime_error propagate for caplog), task backfill (app fixture), anonymization (status_override form contract), task_utils_pii 7/7.

- [x] P3.6: singleton failures green (dataset random, annotation policy, encounter types, strabismus, Remidio ingest/routing/routes, linked grading, camera zip, upload mappings, field workbench)
  CHECK: docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest -q tests/integration/analytics/test_dataset_curation_random.py tests/integration/api/test_project_annotation_policy_html.py tests/unit/test_encounter_set_types.py tests/unit/test_strabismus_disease.py tests/unit/test_remidio_zip_encounter_set_ingest.py tests/unit/remidio_api_integration/test_routing_profiles.py tests/unit/admin/test_linked_grading_admin.py tests/unit/admin/test_camera_zip_uploads.py tests/unit/admin/test_upload_mappings_validation.py tests/unit/field_workbench > /tmp/gate_p36.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: 112 passed 2026-08-28. Root harness fix: tests/conftest.py now aliases sys.modules["tests.conftest"] onto the live conftest module - duplicate module instances were running with an unset _test_db_session, silently routing route writes to a real committing session (order-dependent failures). Also: remidio ingest test rewritten to the package-config contract (app fixture + image/encounter task link shapes).

- [x] P4.1: full `make test` zero failed, zero errors; no new skips/xfails beyond baseline 29/13/1
  CHECK: make test > /tmp/gate_p41.log 2>&1 && echo GATE_OK
  EXPECT: GATE_OK
  EVIDENCE: GREEN 2026-08-28: 1502 passed, 32 skipped, 12 xfailed, 2 xpassed, 0 failed, 0 errors (exit 0). Skip delta +3 = the deferred mobile-PWA tests (recorded reason). Removed 2 stale xfail markers that now XPASS (sensitive-ops renders_logs, filename_anonymization excel sanitization). Anonymization verify_action_creates_task left its xfail (now passes -> counted as xfail retirement).

- [x] P4.2: independent code-quality audit verdict obtained and clean
  EVIDENCE: reviewer verdict READY (overall_correctness=correct): 6 product files audited, 0 security/correctness issues, 4 P3 nits all fixed (duplicate escape_like import, dead sort key, Iterable annotation drift, rate_limiter comment scope).

- [x] P4.3: Beads updated and exported; handoff files refreshed; committed; pushed; branch parity verified
  EVIDENCE: cd6ebd38 (stabilization, 67 files) + 1d2b7da5 (route permissions audit doc + README index) pushed; parity verified. Beads vsa closed, follow-up bead created, issues.jsonl exported. handoff.md/02/03 refreshed. Follow-up audit doc delivered after gate closure.
