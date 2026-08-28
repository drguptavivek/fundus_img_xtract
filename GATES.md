# Gates: Authorization v2 vertical slice 9a - admin user/security reads

- [x] G1: All seven admin user/security read-workspace routes have explicit contracts.
  CHECK: live inventory family test
  EVIDENCE: inventory baseline is 154 Authz v2 HTTP routes and the seven-endpoint family test passes

- [x] G2: User collections use screen admission only and retain query-level hospital scoping.
  CHECK: route catalogue and scoped-list tests
  EVIDENCE: collection routes use admin.users.workspace.view while user detail uses exact admin.users.view; scoped-query regression passes

- [x] G3: User detail binds the exact stored user and local-admin access cannot cross hospital scope.
  CHECK: exact user and cross-hospital truth tables
  EVIDENCE: exact-resource and missing-lineage contract tests pass for admin.users.view

- [x] G4: Role/security diagnostics remain Admin-only and do not grant role mutation authority.
  CHECK: catalogue role tests
  EVIDENCE: explicit domain scenario denies Local Admin, Project PI, Site PI, and Project Admin

- [x] G5: Full Authz/app-init tests, generated parity, static checks, Beads export, commit, rebase, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 837 tests pass; Ruff, Bandit, generated parity, and git diff checks pass; Beads exported before commit
