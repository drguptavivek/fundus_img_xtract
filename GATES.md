# Gates: Lean authorization cutover

Scope: Replace the current authorization engines with role-bound named scope helpers, domain-owned upload/task/grade visibility, one migration, and complete live-route enforcement.

- [x] G1: The public authz API consists of named record and row scoping helpers with role and scope evaluated atomically; missing lineage denies.
  CHECK: uv run pytest tests/unit/authz -q
  EXPECT: /passed/
  EVIDENCE: All 25 lean-authz unit tests passed on 2026-08-28, including missing-fact denial and record/row parity.

- [x] G2: Upload, task, and grade authorization helpers compose the core without moving domain validation into authz; inter-rater visibility returns all grades only for tasks graded by the actor.
  CHECK: uv run pytest tests/unit/authz tests/unit/grading -q
  EXPECT: /passed/
  EVIDENCE: Domain-lineage, upload-profile, exact allocation, media, grade-visibility and worker-revocation tests passed; the broader analytics/grading gate passed 89 tests.

- [x] G3: Project delegation prevents self-escalation, broader scopes, and cross-site grants while implementing the approved PI, Site PI, and Project Admin matrix.
  CHECK: uv run pytest tests/unit/data_authorization/test_project_role_grants.py -q
  EXPECT: /passed/
  EVIDENCE: 8 delegation and grant-containment tests passed; project verifier integration now uses the real role-grant API and configured Project-Lab Unit.

- [x] G4: Exactly one new Alembic revision implements the authorization data changes with real upgrade and downgrade logic, and Alembic retains one head.
  CHECK: make alembic-heads
  EXPECT: /(head)/
  EVIDENCE: `90059e4f7ba5 (head)`; live development DB upgrade, downgrade to `0d3edcf7bc3b`, re-upgrade, and current-head check all passed. A disposable PostgreSQL parity cycle additionally proved that an inactive legacy upload permission remains inactive, an unrelated active collaborator grant remains active, the reconstructed `fileUploader` grant remains inactive, the rollback ledger is removed, and re-upgrade succeeds.

- [x] G5: Every live data-bearing HTTP route and worker is protected through a named scope helper or an approved exact credential/domain boundary; no public prefix exemption or legacy authorization bypass remains.
  CHECK: uv run pytest tests/security/test_authz_route_coverage.py -q
  EXPECT: /passed/
  EVIDENCE: Route coverage and exact-credential tests passed; worker reauthorization tests deny missing, inconsistent, or revoked actor facts and permit exact current scope.

- [x] G6: The old action catalogue, TOML registry, generic policy engine, duplicate project policy engine, and master-admin bypass are absent from live authorization decisions.
  CHECK: sh -c '! test -e authz/actions && ! test -e authz/policies.py && ! test -e authz/registry.py && ! test -e data_authorization/policy.py && ! rg -n "roles_or_project_grant_required|global_uploader_or_project_assignment_required|getattr\([^)]*is_master_admin|\.is_master_admin" --glob "*.py" --glob "!tests/**"'
  EXPECT: /^$/
  EVIDENCE: Legacy-module and live-source scans returned no matches. Compatibility response fields named `is_master_admin` are computed solely from the explicit `admin` role.

- [x] G7: Single-object and SQL-list scope decisions agree across self, Lab Unit, hospital, project, Project-Lab Unit, project-wide, and admin paths.
  CHECK: uv run pytest tests/unit/authz/test_scope_parity.py -q
  EXPECT: /passed/
  EVIDENCE: 3 parity tests plus WAI, discrepancy and direct-image KPI SQL-scope tests passed.

- [x] G8: The full Docker test suite is executed and authorization failures are separated from unrelated baseline/harness failures; affected authorization tests and static checks pass.
  CHECK: make test
  EXPECT: full result recorded; scoped authorization gates pass
  EVIDENCE: Full run: 1,272 passed, 29 skipped, 14 xfailed, 148 failed and 81 errors. A migration test corrupts the shared test schema mid-run; remaining independent failures include longstanding fixture IDs, thumbnail/UI and other unrelated suites. Focused successful gates include 51 passed with 3 skipped and 1 expected failure, 89 analytics/grading tests, 53 Remidio tests, 45 field/allocation/worker tests, 12 exact Remidio-routing tests, and 2 route-coverage tests after a clean test-db rebuild. Compile, static Redis/bypass scans, and diff checks pass. Existing issue `fundus_img_xtract-vsa` tracks full-suite harness repair.

- [x] G9: The authoritative authorization documentation describes the named-helper model and generated/live route coverage without an action catalogue.
  EVIDENCE: `docs/15-DEVELOPMENT/authz_v2_clean_cutover_plan.md` and the concise `docs/policy/authorizations.md`; obsolete ReBAC engine contract removed and README index updated.

- [x] G10: Independent code-quality audit reports no unresolved material authorization defect, and the verified implementation is committed and pushed.
  EVIDENCE: The final independent code-quality/security audit reports no material findings and a `READY` verdict; the integrated implementation is included in the verified closeout commit and push.
