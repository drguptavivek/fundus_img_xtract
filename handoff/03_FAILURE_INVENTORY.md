# Full-suite failure inventory

Baseline snapshot (2026-08-28 morning): 122 failed, 71 errors.
Current: **0 failed, 0 errors** — see `02_CURRENT_STATE.md` for the final
`make test` numbers and `GATES.md` for the gate ledger.

## What the failures were, by family (all resolved)

### A. Shared fixture and authentication contracts — RESOLVED (harness)
- `seed_test_database` committed `test_admin` while `admin_user` re-inserted
  it → get-or-create in the fixture.
- `authenticated_client` set session key `user_id` instead of `_user_id`.
- `UserFactory.create_optometrist` had been dropped in the cutover; rebuilt.
- `test_site_admin_isolation` built a bare Flask app: the login guard now
  comes from patching `flask_login.utils._get_user`; the mock user resolves
  roles like the real model.

### B. Authorization expectation audit — RESOLVED (no policy weakened)
- Encounter-set verify/editor routes: assigned-lab membership alone only
  reaches classical (project-less) records; project-bearing encounters need
  an active `ProjectRoleGrant`. Tests updated to grant it
  (`_grant_project_verify` helper).
- Page routes that are viewer shells assert 200 and put the isolation
  assertion on the JSON API (`/api/encounter-viewer/*` → non-disclosing 404).
- `404 == 403` tests updated to the family's non-disclosing 404 deny.
- Encounter-set-type API routes stay `admin`-only (policy: system
  configuration); tests authenticate as admin.

### C. Encounter verification and editing — RESOLVED (stale fixtures)
- Missing lab assignments on optometrist fixtures; `created_by_id` removed
  from `GradingTask` constructions; save_edit payload uses the nested crop
  schema plus a real base64 image; `status_override` form contract in the
  anonymization workflow.

### D. Mobile uploads — RESOLVED (missing ProjectLabUnit)
- The profile lookup joins an active `ProjectLabUnit`; fixtures now create
  it (plus device approval where the mobile login gate needs it).

### E. Analytics/security isolation and PII — RESOLVED
- Shared `Test Camera` / `Test Disease` / `Test Area` rows are seeded and
  get-or-created; `ExportTaskRow` gained `final_plus_review`;
  `task_utils_pii` patches `clinical_rows` (the removed `scope` symbol).

### F. Thumbnails — RESOLVED (product decision: preserve aspect ratio)
- Tests updated to aspect-preserving sizes; palette/GIF JPEG-encode bug
  fixed in `utils/image_processing.py`; encounter-set thumbnail paths fixed
  in `utils/thumbnail_jobs.py`.

### G. Independent singletons — RESOLVED (see GATES.md P3.6 evidence)
- Sequence `setval` for explicitly seeded IDs, conftest module aliasing,
  deterministic Remidio sync ordering, strabismus `kind='encounter_set'`,
  dataset-curation seeds consensus + refreshes materialized views.

## Deferred by user decision
- Mobile PWA tests (3, skipped with recorded reason).
- `test_upload_schedules_thumbnail_generation` (deleted; endpoint removed).
- Linked-grading hierarchy API no longer rejects inactive diseases —
  product follow-up if the guard is still wanted.
