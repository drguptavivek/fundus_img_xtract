# Gates: Authorization v2 vertical slice 9l - grading inconsistency repair

- [x] G1: All four grading inconsistency diagnostics and repair routes have explicit contracts.
  CHECK: grading-repair inventory family test
  EVIDENCE: inventory is 298 Authz v2 HTTP routes; all three source families classify Authz v2

- [x] G2: Applying review consensus binds the exact grading task.
  CHECK: grading-repair target resolver
  EVIDENCE: missing/invalid task IDs and unresolved Lab Unit scope deny

- [x] G3: Bulk reset is atomic at authorization and bounded.
  CHECK: grading-repair batch regression
  EVIDENCE: empty, duplicate, malformed, oversized, missing, or stale-state member denies the complete target

- [x] G4: Diagnostic screen admission cannot authorize repair.
  CHECK: method-specific inconsistency contract
  EVIDENCE: GET is screen-only and POST requires exact grading_repair_batch

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 959 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
