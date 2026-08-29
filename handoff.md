# Fresh-session handoff

Start here, then read the linked files in order.

## Repository state

- Repository: `fundus_img_xtract`
- Completed checkpoint: `03e954ce` (`Serialize PostgreSQL test database lifecycle`)
- Authorization checkpoint: `ff0fd5a1` (`Replace authorization with lean scoped helpers`)
- Source branch: `vg-work/authz-clean-redesign-2026-08-26`
- Fresh-work branch: `vg-work/full-suite-cleanup`
- Open Beads issue: `fundus_img_xtract-vsa`

The lean authorization cutover and PostgreSQL test-harness repair are committed,
audited, and pushed. The next task is test-suite stabilization without weakening
the new authorization contract.

## Read in this order

1. [`handoff/01_GUARDRAILS.md`](handoff/01_GUARDRAILS.md)
2. [`handoff/02_CURRENT_STATE.md`](handoff/02_CURRENT_STATE.md)
3. [`handoff/03_FAILURE_INVENTORY.md`](handoff/03_FAILURE_INVENTORY.md)
4. [`handoff/04_EXECUTION_PLAN.md`](handoff/04_EXECUTION_PLAN.md)
5. [`handoff/05_START_PROMPT.md`](handoff/05_START_PROMPT.md)
6. [`handoff/06_AUTHZ_RATIONALE_AND_ROUTE_CONTRACT.md`](handoff/06_AUTHZ_RATIONALE_AND_ROUTE_CONTRACT.md)
7. [`handoff/full_suite_failures.txt`](handoff/full_suite_failures.txt)

## Status (2026-08-28, this branch)

Full suite is GREEN: 1502 passed, 32 skipped, 12 xfailed, 2 xpassed,
0 failed, 0 errors. All phases of `04_EXECUTION_PLAN.md` are complete; the
gate ledger with evidence lives in `GATES.md`. Deferred items are recorded
in `02_CURRENT_STATE.md` (PWA security boundary, linked-grading inactive
disease guard, unwired encounter-set thumbnail scheduler).
