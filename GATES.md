# Gates: Authorization v2 vertical slice 9d - maintenance and metadata operations

- [x] G1: All 24 thumbnail, materialized-view, and metadata routes have explicit contracts.
  CHECK: admin maintenance/metadata inventory family test
  EVIDENCE: inventory is 206 Authz v2 HTTP routes; the complete three-file family classifies Authz v2

- [x] G2: Read-only maintenance surfaces retain their distinct role admission.
  CHECK: route catalogue screen-action contracts
  EVIDENCE: thumbnails are Admin/Data Manager, metadata is Admin/Local Admin, and materialized views are Admin-only

- [x] G3: Maintenance mutations cannot use screen admission as mutation authority.
  CHECK: exact system-operation route contracts
  EVIDENCE: every POST uses an exact storage, metadata, or system operation action

- [x] G4: System operation resolution is closed and fail-closed.
  CHECK: system-operation adapter regression
  EVIDENCE: all 14 operation identifiers are closed; raw strings, unknown operations, and missing references resolve to no target

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 867 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
