# Gates: Authorization v2 vertical slice 7 - upload-profile governance

- [x] G1: All 15 upload-profile governance routes and methods have explicit contracts.
  CHECK: targeted catalogue, manifest, and live-consumer inventory tests
  EXPECT: all 15 routes classified, with complete per-method coverage
  EVIDENCE: Inventory family test reports 15/15 authz_v2 and baseline moved to 145 classified HTTP routes.

- [x] G2: Global profile mutation is Admin-only and binds the exact stored profile; missing or forged IDs deny.
  CHECK: route guard and resolver adversarial tests
  EXPECT: collection administration cannot authorize a missing or different profile
  EVIDENCE: Global mutations use admin.upload_profiles.update with the exact System-scoped upload_profile adapter; invalid references deny before DB access.

- [x] G3: Project profile, investigator, assignment, referral, and permission mutation binds the exact governing project and denies cross-project/site escalation.
  CHECK: project role/scope truth tables and endpoint resolver tests
  EXPECT: Project PI, Site PI, and Project Admin authority is limited to their own project/site grants
  EVIDENCE: Project operations use exact project actions; adversarial truth tables prove all three manager roles deny against another project scope.

- [x] G4: Mixed GET/mutation project settings routes use distinct view and manage actions, with incomplete request-body references denied.
  CHECK: method-specific manifest and guard tests
  EXPECT: GET authority cannot authorize POST/PUT and a missing body reference denies
  EVIDENCE: Referral and permission endpoints declare complete GET/POST/PUT method maps with exact project view/manage separation.

- [x] G5: Full Authz/app-init tests, generated policy parity, static checks, Beads export, scoped commit, rebase, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EXPECT: all gates checked with fresh evidence and no pending markers
  EVIDENCE: 831 tests passed; generated policy parity, Ruff, Bandit, diff checks, Beads export, commit, rebase, and push completed.
