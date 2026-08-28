# Gates: Authorization v2 vertical slice 10b - Remidio operational authorization

- [x] G1: All 32 Remidio API routes have explicit contracts.
  CHECK: complete Remidio API inventory family test
  EVIDENCE: inventory is 351 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Attachment OCR reads and mutations use distinct exact authorities.
  CHECK: method-specific route contract and attachment adapter tests
  EVIDENCE: GET resolves view action; POST resolves process action through persisted encounter scope

- [x] G3: Project sync proves the complete active route set and every uploader assignment.
  CHECK: project-sync resolver and relationship provider
  EVIDENCE: missing, empty, duplicate, stale, partial, or widened Lab Unit facts deny

- [x] G4: Project-sync job controls require exact job ownership or scoped admin authority.
  CHECK: job route contracts and existing ownership facts provider
  EVIDENCE: pause, resume, and cancel all resolve the persisted job before decision

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: focused and full Authz/app-init suites pass; generated artifacts and git diff checks pass
