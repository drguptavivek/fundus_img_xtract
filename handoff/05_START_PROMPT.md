# Prompt for the next model

Copy the text below into a fresh Codex session opened on this repository.

---
Work on branch `vg-work/full-suite-cleanup` in
`/Users/vivekgupta/workspace/fundus_img_xtract`.

Read `AGENTS.md`, `handoff.md`, and every file under `handoff/` before editing.
Treat `handoff/01_GUARDRAILS.md` as binding. Continue Beads issue
`fundus_img_xtract-vsa`.

Objective: stabilize the full pytest suite in three stages:

1. repair systemic authentication/shared fixtures, fixed IDs, duplicate seeded
   records, and missing project-Lab Unit relationships;
2. classify genuine regressions versus stale lean-authz expectations without
   weakening fail-closed policy;
3. repair encounter verification, mobile uploads, analytics/security isolation,
   thumbnails, utilities, and remaining singleton failures.

Start with the shared fixture/authentication cluster, not the full suite. For
every `403/404`, trace URL to route/service/authorization/query and determine
which exact fact is missing. Ask the user before changing authorization meaning,
record visibility, disclosure behavior, or domain workflow behavior.

Preserve unrelated dirty files exactly as listed in the guardrails. Use
trace-mcp first for code exploration, `apply_patch` for edits, Compose PostgreSQL
test commands, and `uv run`. Keep the handoff files current. Do not report
completion until focused gates and one final `make test` are green, an independent
code-quality audit is clean, Beads is updated, and changes are committed and
pushed.

---
