# Gates: Authorization v2 vertical slice 17 - project grader allocations

- [x] G1: All 7 project grader-allocation routes have explicit contracts.
  CHECK: grading-allocation inventory family test
  EVIDENCE: inventory is 424 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Proposed allocations bind an existing user to one persisted project site.
  CHECK: project-allocation target resolver tests
  EVIDENCE: missing users and unknown project-site scopes deny

- [x] G3: Existing allocation mutations bind both route identifiers.
  CHECK: project-allocation target resolver tests
  EVIDENCE: an allocation whose persisted project differs from the route project denies

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: capacity/scope compatibility, grader eligibility, derived targets, coverage, and activation remain in grading_allocation

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1120 tests; inventory checks pass
