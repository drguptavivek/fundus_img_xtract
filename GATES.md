# Gates: Authorization v2 vertical slice 9n - scoped admin operations

- [x] G1: All nine remaining admin audit, S3-sync, and task-backfill routes have explicit contracts.
  CHECK: final admin scope-sensitive inventory family test
  EVIDENCE: inventory is 319 Authz v2 HTTP routes; no reviewed route remains unmapped

- [x] G2: Missing or malformed scope facts deny before database resolution.
  CHECK: scope-sensitive adapter fail-closed test
  EVIDENCE: absent hospital, audit identifier, sync identifier, or complete Lab Unit set returns no target

- [x] G3: S3 exact operations resolve persisted hospital lineage and retry state.
  CHECK: S3 query and record adapters
  EVIDENCE: status queries require a hospital; retry requires a persisted failed sync and its persisted configuration

- [x] G4: Task backfill cannot span undeclared or mixed hospital scope.
  CHECK: task-backfill target adapter
  EVIDENCE: unique bounded Lab Unit IDs must all resolve to the declared hospital

- [x] G5: Live local-admin hospital derivation uses Hospital IDs, not Lab Unit IDs.
  CHECK: S3 dashboard helper implementation
  EVIDENCE: distinct non-null lab_unit.hospital_id values are returned

- [x] G6: Full Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 991 tests pass after baseline refresh; generated artifacts and git diff checks pass
