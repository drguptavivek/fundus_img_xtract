# Gates: Authorization v2 vertical slice 9m - global rate limits and upload configuration

- [x] G1: All 12 rate-limit and upload-configuration entry routes have explicit contracts.
  CHECK: global admin entry inventory family test
  EVIDENCE: inventory is 310 Authz v2 HTTP routes; all named routes classify Authz v2

- [x] G2: Rate-limit mutation cannot borrow dashboard admission.
  CHECK: route catalogue actions
  EVIDENCE: reads are screen-only; clear-one and clear-all require closed exact operations

- [x] G3: Project upload workspace binds the exact stored project.
  CHECK: upload project workspace contract
  EVIDENCE: project list uses grant admission; workspace uses project.view with project resolver

- [x] G4: Upload profile and metadata entry pages retain their narrower screen actions.
  CHECK: route catalogue contracts
  EVIDENCE: profile, project-list, project-workspace, and metadata pages use distinct authorities

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 960 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
