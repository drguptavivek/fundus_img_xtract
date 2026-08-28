# Gates: Authorization v2 vertical slice 12 - browser authentication boundary

- [x] G1: All 11 browser-authentication routes have explicit contracts.
  CHECK: browser authentication inventory family test
  EVIDENCE: inventory is 375 Authz v2 HTTP routes; the complete family classifies v2

- [x] G2: Public entry is separated from credential-bearing reset operations.
  CHECK: route catalogue contract construction and family assertions
  EVIDENCE: login/request entry is public; reset completion and status use an exact signed credential

- [x] G3: Authenticated session operations authorize the exact current user.
  CHECK: route catalogue resolver assertions
  EVIDENCE: logout, keepalive, and reauthentication require the user resolver

- [x] G4: Application-domain rules remain outside Authz v2.
  CHECK: catalogue and route-policy diff review
  EVIDENCE: no CAPTCHA, OTP, password-policy, throttling, or workflow validation was added to Authz v2

- [x] G5: Authz/app-init tests, generated parity, diff checks, Beads export, commit, remote ancestry, and push succeed.
  CHECK: node /Users/vivekgupta/.agents/skills/unlazy/scripts/gate-check.mjs GATES.md
  EVIDENCE: full Authz/app-init suite passes 1092 tests; generated parity and inventory checks pass
