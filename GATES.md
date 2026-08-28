# Gates: Authorization v2 vertical slice 9c - system status and dependency security

- [x] G1: All 21 status, CVE, and package-update routes have explicit contracts.
  CHECK: admin system-status/scanner inventory family test
  EVIDENCE: inventory is 182 Authz v2 HTTP routes; the complete three-file family classifies Authz v2

- [x] G2: Read-only status surfaces retain their distinct role admission.
  CHECK: route catalogue screen-action contracts
  EVIDENCE: system status is Admin/Data Manager, vulnerability reports are Admin/Local Admin, and sensitive histories are Admin-only

- [x] G3: Sequence and dependency refreshes cannot use screen admission as mutation authority.
  CHECK: exact system-operation route contracts
  EVIDENCE: all three POST routes require admin.system.operation with an exact resource

- [x] G4: System operation resolution is closed and fail-closed.
  CHECK: system-operation adapter regression
  EVIDENCE: raw strings, unknown operations, and missing references resolve to no target

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 856 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
