# Gates: Authorization v2 vertical slice 14 - grading-scheme API

- [x] G1: All 10 grading-scheme API routes have explicit contracts.
  CHECK: grading-scheme inventory family test
  EVIDENCE: inventory is 395 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Every existing scheme mutation resolves the exact persisted scheme.
  CHECK: route resolver assertions and grading-config adapter tests
  EVIDENCE: update, duplicate, delete, and grade creation use the grading-config resolver

- [x] G3: Grade path identifiers are parent-bound and fail closed.
  CHECK: grading-scheme grade lineage test
  EVIDENCE: a persisted grade with a different disease/scheme parent denies

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: core-scheme protection, link/use blockers, field rules, sanitization, and activation remain application-service rules

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1116 tests; generated parity and inventory checks pass
