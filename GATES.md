# Gates: Authorization v2 vertical slice 9h - lookup governance

- [x] G1: All 15 hospital, Lab Unit, disease, camera, and area routes have method-aware contracts.
  CHECK: admin lookup-governance inventory family test
  EVIDENCE: inventory is 257 Authz v2 HTTP routes; the complete lookup family classifies Authz v2

- [x] G2: Lookup collection reads cannot authorize create, edit, or delete.
  CHECK: method-specific route contracts
  EVIDENCE: list GETs are screen-only, list POSTs are closed creation operations, and row changes are exact

- [x] G3: Lookup rows require typed exact identities and authoritative scope.
  CHECK: lookup adapter regression and resolver implementation
  EVIDENCE: bare integers and unknown kinds deny; hospital and Lab Unit lineage is server-resolved

- [x] G4: Global versus organizational lookup scope remains explicit.
  CHECK: lookup resolver scope branches
  EVIDENCE: disease/camera/area resolve System; hospital/Lab Unit resolve stored hierarchy

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 917 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
