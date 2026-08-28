# Gates: Authorization v2 vertical slice 6 - direct uploads

- [x] G1: Every direct-upload HTTP method has an explicit Authz v2 contract; no mixed endpoint can reuse GET screen admission for POST.
  CHECK: targeted catalogue, manifest, and live-consumer inventory tests
  EXPECT: all 13 direct-upload routes classified, with complete per-method coverage
  EVIDENCE: Inventory reports 13/13 direct-upload routes as authz_v2; method-policy tests reject a mixed endpoint with any unclassified method.

- [x] G2: Direct upload reads, edits, image mutations, and jobs bind exact stored resources; missing, forged, cross-site, or cross-owner facts deny.
  CHECK: route guard and resolver adversarial tests
  EXPECT: no collection/screen decision authorizes an individual upload, image, or job
  EVIDENCE: Route contracts use direct_image_upload/job resources; bounded batch resolution rejects empty, invalid, over-limit, missing, or cross-hospital sets.

- [x] G3: Upload and pregraded submissions authorize the complete upload-profile tuple while kind/disease/camera/area/mydriatic validation remains application-owned.
  CHECK: upload-target truth tables and missing-fact tests
  EXPECT: incomplete authorization tuples deny before handler execution
  EVIDENCE: Both pregraded POST methods require the exact upload_target resolver; existing upload-profile relationship and missing-reference truth tables pass.

- [x] G4: Lab/hospital option APIs expose only upload-profile-authorized information and deny cross-user, cross-site, and incomplete calls.
  CHECK: option-resource resolver and route tests
  EXPECT: no broad role or page admission can reveal an unauthorized option
  EVIDENCE: Both option endpoints require the exact self upload-options user action; handlers retain profile-projected Lab Unit membership checks.

- [x] G5: Full Authz/app-init tests, generated policy parity, static checks, Beads export, scoped commit, rebase, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EXPECT: all gates checked with fresh evidence and no pending markers
  EVIDENCE: 824 tests passed; generated artifacts, Ruff, Bandit, diff checks, Beads export, scoped commit, rebase, and push completed.
