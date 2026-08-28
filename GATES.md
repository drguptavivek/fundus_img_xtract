# Gates: Authorization v2 vertical slice 8 - project role grants

- [x] G1: Both project role-grant API routes have complete method-specific Authz v2 contracts.
  CHECK: live inventory and method-policy tests
  EXPECT: GET cannot authorize create/update/delete
  EVIDENCE: Inventory reports both routes authz_v2; GET uses project.grants.view and all mutation methods use authorization.grants.manage.

- [x] G2: Grant listing requires a containing project-scoped manager grant.
  CHECK: project grant-view truth tables
  EXPECT: cross-project and cross-site reads deny
  EVIDENCE: project.grants.view is an exact project action governed by scoped roles and exact-resource containment.

- [x] G3: Create/update/delete bind an exact grant target and enforce delegable-by plus own-scope containment.
  CHECK: delegation and grant-target adversarial tests
  EXPECT: PI/Site PI cannot grant PROJECT_PI or SITE_PI, cannot grant outside own scope, and may grant PROJECT_ADMIN only inside own scope
  EVIDENCE: Existing delegation service truth tables cover PI/Site PI Project Admin grants, cross-project/site denial, and leadership-role denial.

- [x] G4: Missing body facts, mismatched project/grant IDs, unknown roles, and invalid scopes deny.
  CHECK: grant target resolver tests
  EXPECT: incomplete or inconsistent targets never reach mutation handlers
  EVIDENCE: Every mutation requires the exact grant_target resolver; unknown actions, invalid references, and incomplete resolver output fail closed.

- [x] G5: Full Authz/app-init tests, generated parity, static checks, Beads export, commit, rebase, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EXPECT: all gates checked with fresh evidence
  EVIDENCE: 837 full Authz/app-init tests passed; generated parity, Ruff, Bandit, diff checks, Beads, commit, rebase, and push passed.
