# Gates: Authorization v2 vertical slice 11b - grading workbench acquisition

- [x] G1: All 13 grading-workbench routes have explicit contracts.
  CHECK: complete grading-workbench inventory family test
  EVIDENCE: inventory is 364 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Queue acquisition fails closed without complete selection scope.
  CHECK: acquisition reference and adapter tests
  EVIDENCE: disease set, role slot, and Lab Unit are mandatory and validated

- [x] G3: Exact task, revision, and package acquisitions derive one persisted scope.
  CHECK: acquisition resolver
  EVIDENCE: missing identifiers, tasks, packages, or mixed-scope task sets deny

- [x] G4: Every disease requires active grading eligibility; revision also requires ownership.
  CHECK: acquisition facts provider and generated catalogue
  EVIDENCE: aggregate grading-slot evidence covers the exact target; revision has a distinct owner path

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: focused and full Authz/app-init suites pass; generated artifacts and git diff checks pass
