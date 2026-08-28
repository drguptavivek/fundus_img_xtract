# Gates: Authorization v2 vertical slice 16 - application utility routes

- [x] G1: All 13 application-root route rules have explicit contracts.
  CHECK: app.py utility route inventory family test
  EVIDENCE: inventory is 417 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Every route is explicitly public rather than path-prefix inferred.
  CHECK: per-endpoint mode and action assertions
  EVIDENCE: every distinct endpoint uses PUBLIC mode and public.view

- [x] G3: Duplicate mobile PWA rules share one reviewed endpoint contract.
  CHECK: runtime inventory and endpoint-name set
  EVIDENCE: both /mobile/ URL rules classify through _mobile_pwa

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: file containment, redirects, rate limiting, health checks, sitemap generation, and rendering remain app.py rules

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1118 tests; inventory checks pass
