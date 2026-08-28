# Gates: Authorization v2 vertical slice 9i - grading configuration governance

- [x] G1: All 20 grading-definition and eligibility routes have explicit contracts.
  CHECK: admin grading-configuration inventory family test
  EVIDENCE: inventory is 277 Authz v2 HTTP routes; all five source families classify Authz v2

- [x] G2: Persisted grading definitions require typed exact identities.
  CHECK: grading-config adapter regression
  EVIDENCE: bare IDs, invalid IDs, and unknown kinds deny before database access

- [x] G3: Creation and hierarchy-wide changes cannot borrow list admission.
  CHECK: method-specific contracts and closed operation allowlist
  EVIDENCE: disease/linked creation and linked hierarchy updates have distinct exact operations

- [x] G4: Eligibility mutations bind the exact user and hospital scope.
  CHECK: exact eligibility user action
  EVIDENCE: Admin/Local Admin authority is evaluated against the server-resolved user; missing user facts deny

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 934 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
