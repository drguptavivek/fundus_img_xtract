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

## Immediate objective

Repair the remaining full-suite failures in dependency order:

1. shared authentication/fixture/fixed-ID/project-Lab Unit contracts;
2. authorization expectation classification, preserving fail-closed policy;
3. encounter verification, mobile uploads, analytics/security isolation,
   thumbnails, and utilities.

For every failure, decide explicitly whether it is a harness defect, a stale
test expectation, or a genuine product regression. Ask the user before changing
any authorization or domain meaning.
