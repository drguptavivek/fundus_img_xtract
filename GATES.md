# Gates: Authorization v2 vertical slice 11a - grading workbench sessions

- [x] G1: All eight self-list and durable-session lifecycle routes have explicit contracts.
  CHECK: grading-workbench session inventory family test
  EVIDENCE: inventory is 359 Authz v2 HTTP routes; all eight reviewed routes classify v2

- [x] G2: Session UUIDs alone never authorize credential-bearing operations.
  CHECK: workbench session adapter and catalogue truth tables
  EVIDENCE: view, heartbeat, release, draft, and submit require owner, active lease, token, and generation

- [x] G3: Session scope is the common persisted scope of every leased target.
  CHECK: workbench session resolver
  EVIDENCE: missing tasks, unresolved scope, or mixed-scope target sets deny

- [x] G4: Clinical grading sessions have no administrator break-glass path.
  CHECK: generated catalogue and role/action matrix
  EVIDENCE: session paths require scoped grading qualification and persisted ownership

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: focused and full Authz/app-init suites pass; generated artifacts and git diff checks pass
