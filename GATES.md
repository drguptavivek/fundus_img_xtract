# Gates: Authorization v2 vertical slice 19 - API documentation surfaces

- [x] G1: All 6 documentation routes have explicit contracts.
  CHECK: documentation inventory family test
  EVIDENCE: inventory is 437 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Public access is declared per endpoint.
  CHECK: endpoint mode assertions
  EVIDENCE: every docs/routes.py and docs/swagger_ui.py endpoint uses PUBLIC mode

- [x] G3: Documentation uses its dedicated canonical action.
  CHECK: endpoint action assertions
  EVIDENCE: every route uses docs.api.view rather than generic path inference

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: Markdown rendering, OpenAPI construction, Swagger assets, and formatting remain in docs modules

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1128 tests; inventory checks pass
