# Gates: Authorization v2 vertical slice 5 - Remidio workspaces and job control

Scope: Migrate all 13 Remidio API upload/workspace routes with exact job, encounter-set, disclosure, and inference authority. Direct uploads remain the next independent slice because mixed GET/POST routes require separate exact-mutation handling.

- [x] G1: All 13 routes have explicit endpoint contracts and none remains legacy-unmapped.
  CHECK: targeted live-consumer inventory test
  EXPECT: family 13/13 authz_v2 and legacy_unmapped reduced by 13
  EVIDENCE: Inventory family test requires 13/13 classified; authz_v2=117 and legacy_unmapped=516.

- [x] G2: Browser and sync workspaces are screen admission only; selected encounter-set rows and downloads remain list-scoped or exactly authorized.
  CHECK: route contract and catalogue truth-table tests
  EXPECT: screen permission cannot authorize a row, attachment, or archive download
  EVIDENCE: Dedicated masked/PII workspace actions are admission only; delivery routes use exact encounter-set actions.

- [x] G3: Attachment/download and job status routes bind exact stored resources with correct disclosure and ownership/scope rules.
  CHECK: exact-resource, disclosure, owner and cross-scope denial tests
  EXPECT: forged IDs, cross-site resources, and missing lineage deny
  EVIDENCE: Attachment/archive policies require exact parent encounter-set resolution; job page/status require exact job ownership/scope policy.

- [x] G4: Wadhwani inference mutations use a closed exact project/target action binding; page/workspace admission cannot authorize execution.
  CHECK: action/resolver mapping tests
  EXPECT: mutation actions are distinct from screens and job views
  EVIDENCE: Run route declares a closed project.wai.run/inference.wai.run binding; pages use summary admission and jobs use jobs.result.view.

- [x] G5: Full Authz/app-init tests, generated policy parity, Ruff, Bandit, diff checks, direct adversarial review, Beads export, scoped commit, pull/rebase, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EXPECT: all gates checked with fresh evidence and no pending markers
  EVIDENCE: 805 tests passed; generated artifacts, Ruff, Bandit, diff checks, and direct adversarial review passed. Beads, commit, rebase, and push are recorded in repository history.
