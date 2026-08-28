# Gates: Authorization v2 vertical slice 21 - glaucoma AI upload API

- [x] G1: All 7 glaucoma AI upload routes have explicit contracts.
  CHECK: glaucoma AI API inventory family test
  EVIDENCE: inventory is 448 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Mobile result and media reads require exact persisted ownership.
  CHECK: UUID resolver and route-policy assertions
  EVIDENCE: result, image, and thumbnail use direct_image_upload plus mobile owner action

- [x] G3: Mobile and browser upload creation have distinct channel contracts.
  CHECK: route mode/action assertions and catalogue construction
  EVIDENCE: JWT route requires MOBILE_SESSION; browser route uses protected session upload action

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: disease/model/profile/camera/area/mydriatic/file/task/inference rules remain in application services

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1144 tests; generated parity and inventory checks pass
