# Gates: Authorization v2 vertical slice 10a - Remidio API configuration

- [x] G1: All 25 administrator-only Remidio API configuration routes have explicit contracts.
  CHECK: Remidio API configuration inventory family test
  EVIDENCE: inventory is 344 Authz v2 HTTP routes; all 25 reviewed routes classify v2

- [x] G2: Persisted configuration identities are typed and fail closed.
  CHECK: Remidio configuration adapter tests
  EVIDENCE: bare, unknown-kind, zero, missing, or broken-lineage references return no target

- [x] G3: Project and system scope come from persisted Remidio lineage.
  CHECK: Remidio configuration adapter
  EVIDENCE: project-owned records resolve project scope; genuinely global connections resolve system scope

- [x] G4: Creation and upsert routes cannot borrow a list permission.
  CHECK: route catalogue contracts and closed operation resolver
  EVIDENCE: seven create/upsert endpoints require declared closed system-operation identities

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: focused and full Authz/app-init suites pass; generated artifacts and git diff checks pass
