# Gates: Authorization v2 vertical slice 13 - project remote inference

- [x] G1: All 10 project remote-inference routes have explicit contracts.
  CHECK: remote-inference inventory family test
  EVIDENCE: inventory is 385 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Batch execution has an exact bounded target and one scope.
  CHECK: remote-inference batch resolver tests
  EVIDENCE: empty, duplicate, oversized, missing, cross-project, and mixed-scope inputs deny

- [x] G3: Job resume resolves an external token to one persisted scoped job.
  CHECK: job reference validation and route resolver assertion
  EVIDENCE: blank or unknown tokens deny; route uses the job resolver

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: model compatibility, clinical eligibility, job staleness, and requeue behavior remain application-service rules

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1114 tests; generated parity and inventory checks pass
