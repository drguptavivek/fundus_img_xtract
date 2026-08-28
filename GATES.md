# Gates: Authorization v2 vertical slice 22 - glaucoma AI browser workspace

- [x] G1: All 4 glaucoma AI browser workspace routes have explicit contracts.
  CHECK: browser workspace inventory family test
  EVIDENCE: inventory is 452 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Workspace admission cannot stand in for row authorization.
  CHECK: endpoint mode assertions
  EVIDENCE: every endpoint is SCREEN with screen_entry enforcement

- [x] G3: Exact result/media authority remains separate.
  CHECK: route catalogue separation
  EVIDENCE: workspace uses upload.workspace.view while UUID routes retain owner-bound exact actions

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: option derivation, executable-model filtering, pagination, and mydriatic presentation remain in application modules

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1145 tests; inventory checks pass
