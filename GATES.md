# Gates: Authorization v2 vertical slice 9g - operational storage and quotas

- [x] G1: All eight log, quarantine, disk, and quota routes have explicit contracts.
  CHECK: admin operational-storage inventory family test
  EVIDENCE: inventory is 242 Authz v2 HTTP routes; the complete four-file family classifies Authz v2

- [x] G2: Operational read surfaces cannot authorize mutations.
  CHECK: screen versus protected route contracts
  EVIDENCE: logs, quarantine, disk reports, and quota lists use screen admission only

- [x] G3: Quota changes bind the exact stored user.
  CHECK: upload-quota exact action contract
  EVIDENCE: update requires admin.upload_quota.manage with the user resolver

- [x] G4: Destructive disk cleanup uses closed Admin-only operations.
  CHECK: system-operation allowlist
  EVIDENCE: duplicate and processed-ZIP deletion have distinct recognized identifiers; unknown operations deny

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 905 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
