# Gates: Authorization v2 vertical slice 9f - database export and restore

- [x] G1: All eight database dump, Excel export, and restore routes have explicit contracts.
  CHECK: admin database-movement inventory family test
  EVIDENCE: inventory is 234 Authz v2 HTTP routes; the complete three-file family classifies Authz v2

- [x] G2: Database information pages cannot authorize data movement.
  CHECK: method-specific export contracts
  EVIDENCE: GET uses screen admission while POST requires exact admin.database.export

- [x] G3: Restore upload, execution, and cancellation use a distinct exact action.
  CHECK: restore route contracts
  EVIDENCE: all three lifecycle routes require admin.database.restore, including GET cancellation

- [x] G4: Database operations are closed and retain reauthentication where present.
  CHECK: system-operation allowlist and route decorators
  EVIDENCE: five database operations are allowlisted; dump and Excel export retain requires_reauth

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 899 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
