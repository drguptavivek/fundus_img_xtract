# Gates: Authorization v2 vertical slice 15 - encounter-set-type API

- [x] G1: All 9 encounter-set-type API routes have explicit contracts.
  CHECK: encounter-set-type inventory family test
  EVIDENCE: inventory is 404 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Every existing record read and mutation resolves the persisted type.
  CHECK: route resolver assertions and grading-config adapter tests
  EVIDENCE: get, schema export, update, state changes, and both delete forms use the grading-config resolver

- [x] G3: Creation is a closed named system operation.
  CHECK: system-operation reference registry and route contract
  EVIDENCE: encounter_set_type_create is the only accepted creation reference for this route

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: schema generation, validation, state transitions, delete blockers, and filename safety remain application-service rules

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1117 tests; inventory checks pass
