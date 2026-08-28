# Gates: Authorization v2 vertical slice 9b - admin user mutations

- [x] G1: All seven admin user/device mutation routes have explicit method-specific or exact-resource contracts.
  CHECK: admin mutation inventory family test
  EVIDENCE: inventory is 161 Authz v2 HTTP routes; all seven routes classify Authz v2

- [x] G2: Account creation binds the hospital and complete requested grant set.
  CHECK: user_creation_target adapter and delegation tests
  EVIDENCE: malformed, missing, cross-hospital, wrong-scope, and non-delegable role facts deny

- [x] G3: User edits, activation, password reset, enrolment, and device changes require an exact stored user.
  CHECK: method contract and exact-resource tests
  EVIDENCE: GET admission is separated from POST; every mutation uses an exact resource action

- [x] G4: Admin mobile-session revocation verifies both the stored session and URL user lineage.
  CHECK: AdminMobileSessionTargetRef resolver path
  EVIDENCE: a session whose stored user differs from the supplied user reference resolves to no target

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 845-test full suite plus the added session-lineage regression pass; Ruff, Bandit, generated parity, and git diff checks pass
