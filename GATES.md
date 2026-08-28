# Gates: Authorization v2 vertical slice 18 - browser direct-upload API

- [x] G1: All 7 browser direct-upload API routes have explicit contracts.
  CHECK: direct-upload API inventory family test
  EVIDENCE: inventory is 431 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Lab Unit disclosure binds classical or explicit project context.
  CHECK: upload Lab Unit resolver tests
  EVIDENCE: invalid or unknown project context denies; valid classical and project-site scopes remain distinct

- [x] G3: Upload creation and job reads use exact target contracts.
  CHECK: route resolver assertions
  EVIDENCE: creation uses upload_target and status endpoints use job

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: profile, camera, disease, area, mydriatic, file, quota, duplicate, and inference rules remain in services.uploads.direct

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1127 tests; generated parity and inventory checks pass
