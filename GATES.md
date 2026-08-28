# Gates: Authorization v2 vertical slice 9k - executable configuration

- [x] G1: All eight AI-model and Celery-schedule routes have method-aware contracts.
  CHECK: executable-configuration inventory family test
  EVIDENCE: inventory is 294 Authz v2 HTTP routes; both source families classify Authz v2

- [x] G2: Stored executable configuration requires typed exact identity.
  CHECK: executable-config adapter regression
  EVIDENCE: bare IDs, unknown kinds, invalid IDs, and missing rows deny

- [x] G3: List and creation access cannot authorize row mutation.
  CHECK: method-specific route contracts
  EVIDENCE: lists use screen admission, creates use closed operations, edits/deletes use exact records

- [x] G4: Health testing and scheduler mutation bind persisted targets.
  CHECK: exact action contracts
  EVIDENCE: health, update, and delete routes require executable_config_record resolution

- [x] G5: Full Authz/app-init tests, generated parity, static/security checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: 947 tests pass; Ruff, Bandit, generated parity, and git diff checks pass
