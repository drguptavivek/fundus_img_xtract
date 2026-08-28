# Gates: Authorization v2 vertical slice 9j - Remidio operational administration

- [x] G1: All nine Remidio admin, migration, and IITK routes have explicit contracts.
  CHECK: admin Remidio operations inventory family test
  EVIDENCE: inventory is 286 Authz v2 HTTP routes; all three source families classify Authz v2

- [x] G2: Remidio dashboards and status endpoints remain read-only admission.
  CHECK: route catalogue screen contracts
  EVIDENCE: eight routes use Admin-only security-screen authority

- [x] G3: Stuck-upload cleanup cannot borrow dashboard admission.
  CHECK: cleanup exact route contract
  EVIDENCE: POST requires admin.system.operation and exact system_operation resolution

- [x] G4: Cleanup operation identity is closed and fail-closed.
  CHECK: system-operation allowlist
  EVIDENCE: remidio_stuck_upload_cleanup is explicit; arbitrary operation text denies

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 935 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
