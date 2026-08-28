# Gates: Authorization v2 vertical slice 20 - self-service account routes

- [x] G1: All 4 account routes have explicit contracts.
  CHECK: account route inventory family test
  EVIDENCE: inventory is 441 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Profile read and update are method-specific.
  CHECK: profile action assertions
  EVIDENCE: GET uses account.profile.view and POST uses account.profile.update

- [x] G3: Password operations resolve only the current user.
  CHECK: password endpoint resolver assertions
  EVIDENCE: both password routes use the user resolver and self-only action

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: input validation, password verification/strength/history, session rotation, and messaging remain in account code

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1129 tests; inventory checks pass
