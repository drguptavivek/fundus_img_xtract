# Full-suite failure inventory

The exact failing/error test identifiers are in `full_suite_failures.txt`.
The source log for the producing session was `/tmp/fundus-full-test.log`; rerun
`make test` rather than relying on that temporary file in a new environment.

## Largest families by file

| Count | File |
|---:|---|
| 18 | `tests/integration/test_encounter_set_editor.py` |
| 17 | `tests/integration/test_verify_encounter_set_routes.py` |
| 10 | `tests/unit/api/test_encounter_set_csrf_protection.py` |
| 9 | `tests/unit/api/test_encounter_set_race_conditions.py` |
| 8 | `tests/unit/verify_encounter_set/test_input_validation.py` |
| 8 | `tests/unit/verify_encounter_set/test_hospital_scoping.py` |
| 7 | `tests/unit/utils/test_task_utils_pii.py` |
| 6 | `tests/integration/thumbnails/test_thumbnail_image_processing.py` |
| 6 | `tests/integration/common/test_runner.py` |
| 6 | `tests/integration/common/test_runner_pytest.py` |
| 4 | `tests/integration/auth/test_login_fixtures.py` |
| 4 | `tests/integration/security/test_reauth_decorator.py` |
| 4 | `tests/integration/security/test_sensitive_exports.py` |
| 4 | `tests/unit/api/test_mobile_uploads.py` |
| 4 | `tests/unit/auth/test_site_admin_isolation.py` |
| 4 | `tests/unit/security/test_analytics_isolation.py` |
| 4 | `tests/unit/services/test_thumbnail.py` |
| 4 | `tests/unit/test_user_fixtures.py` |

## Initial classification

### A. Shared fixture and authentication contracts

Symptoms include missing/incorrect login fixtures, seeded users without current
roles or relationships, fixed-ID collisions, foreign-key/unique violations,
and tests constructing partial Flask apps without `login_manager`.

Start here because correcting shared factories may collapse failures in several
later families. Do not reintroduce legacy `master_admin` semantics.

### B. Authorization expectation audit

Several tests now receive `403` or `404` after lean authz. For each:

1. identify the exact route and named scope helper;
2. construct the complete intended project/Lab/profile/grading relationship;
3. verify whether the request should pass under current policy;
4. update stale fixtures/tests when facts are incomplete;
5. change product authorization only after explicit user approval.

Mobile PWA public routing is a separate credential/channel decision and must
not be inferred from upload permissions.

### C. Encounter verification and editing

This is the largest domain cluster. Likely mixtures include missing project-Lab
membership, upload-profile configuration, route lineage, current workflow
state, and genuinely stale response/status expectations. Run editor, verify,
CSRF, race-condition, input-validation, and hospital-scoping files as one branch
after shared fixtures are stable.

### D. Mobile uploads and device enrolment

The `403` upload responses likely indicate fixtures no longer provide active
upload-profile assignment plus exact Lab/project relationships. Validate facts
before touching authorization. Device-session tests also show seeded uniqueness
and revocation-store assumptions.

### E. Analytics/security isolation and PII

Failures include fixed relationship IDs, missing DTO fields, obsolete mock
shapes, and at least one cross-hospital expectation requiring adversarial review.
Never solve these by broad-loading then filtering or by restoring admin bypasses.

### F. Thumbnail and utility contracts

Thumbnail tests expect square dimensions while implementation preserves aspect
ratio; this is a product expectation decision, not automatically a bug. Ask the
user before changing behavior. Utility failures include stale monkeypatch
targets, request-context assumptions, error logging, materialized-view order,
filename validation, and task-backfill status.

### G. Independent singletons

The inventory includes isolated failures in dataset randomness, KPI API,
annotation policy HTML, encounter types, strabismus, Remidio ZIP ingest,
grading history validation, and Remidio route ordering. Address these only after
systemic fixtures are corrected and rerun, because many may disappear.
