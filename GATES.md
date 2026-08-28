# Gates: Authorization v2 vertical slice 9e - credential and application configuration

- [x] G1: All 20 email, S3, and application-setting routes have explicit method-aware contracts.
  CHECK: admin configuration inventory family test
  EVIDENCE: inventory is 226 Authz v2 HTTP routes; the complete three-file family classifies Authz v2

- [x] G2: Stored credential configuration access binds exact persisted rows.
  CHECK: email-settings and S3 resource adapters
  EVIDENCE: missing/invalid IDs and absent active email configuration resolve to no target

- [x] G3: Mixed GET/POST routes separate page admission from mutation authority.
  CHECK: method-specific configuration contract test
  EVIDENCE: all five combined routes use screen/exact or exact-read/exact-manage pairs

- [x] G4: Candidate config operations and global settings updates are closed exact operations.
  CHECK: system-operation allowlist and exact action contracts
  EVIDENCE: unknown operations and undeclared candidate behavior deny

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 888 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
