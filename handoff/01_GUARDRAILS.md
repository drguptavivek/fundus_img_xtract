# Guardrails

These constraints are authoritative for the next session.

## Authorization

- Fail closed whenever required identity, role, scope, resource, lineage,
  relationship, state, credential, or channel facts are missing.
- Routes select explicit named authorization behavior and supply all required
  facts. Do not infer missing scope from broad roles.
- Keep domain validation outside `authz`. Disease, camera, area, mydriatic
  state, grading rules, upload contents, and workflow state remain in their
  owning application modules.
- Upload-profile assignment is authorization to use that profile. Validation
  of finer upload details remains domain logic.
- Single-record checks and SQL list predicates must use equivalent facts.
- No Redis-backed identity, role, scope, authorization decision, or protected
  row-set cache. OCR/image-metadata computation caches may remain only after
  live resource authorization.
- Do not restore the deleted action catalogue, TOML registry, generic policy
  engine, ReBAC engine, compatibility fallback, or master-admin bypass.
- `PROJECT_PI` and `SITE_PI` are delegable only by `ADMIN`.
- `PROJECT_ADMIN` is delegable by `PROJECT_PI` or `SITE_PI` only within the
  delegator's exact project/site scope. Cross-site, broader-scope, and
  self-escalating grants must deny.
- Preserve inter-rater behavior: a grader can see their own grades and all
  grades attached to tasks they graded, but not unrelated tasks.
- `pii_exporter` directly authorizes masked or identifier-bearing project
  export within its exact grant scope; it does not also need `data_exporter`.
  Classical identifier release is Admin break-glass only. Missing, malformed
  or mixed-scope requests deny in full, and PII release requires step-up plus
  a sensitive-operation audit record.
- Follow `07_POLICY_DECISIONS.md`; do not restore contradictory additive-PII
  or observer-only-PI language.

## Migration and persistence

- Keep exactly one new authorization migration:
  `90059e4f7ba5_lean_authorization_cutover.py`.
- Do not add follow-on authorization migrations to conceal defects in that
  migration. Correct it directly until cutover.
- Upgrade and downgrade must remain real, idempotent where required, and
  loss-aware. Inactive legacy upload authority must remain inactive on rollback.
- Destructive migration tests must use a unique disposable database, never the
  shared `fundus_test` schema.

## Testing

- Use `uv run`; never bare `python`.
- Run PostgreSQL tests inside Compose:
  `docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest ...`
- Prefer `make test` for the final full-suite gate.
- The shared test database is serialized by a PostgreSQL advisory lock in
  `tests/conftest.py`. Do not remove or bypass it.
- Do not change correct application behavior merely to satisfy stale tests.
  Classify first, then update the test or product deliberately.
- Do not turn failures into skips/xfails unless the user explicitly approves
  that outcome and the reason is recorded.

## Repository hygiene

- Preserve these user-owned unrelated changes and do not stage them:
  `.claude/settings.json`, `CLAUDE.md`, `.claude/launch.json`, `.serena/`, and
  `:memory:.ses`.
- Use `apply_patch` for file edits.
- Use trace-mcp before code exploration, as required by `AGENTS.md`.
- Track work in Beads issue `fundus_img_xtract-vsa`; export
  `.beads/issues.jsonl` before committing.
- After verified implementation: independent code-quality audit, commit,
  `git pull --rebase --autostash`, push, and verify branch parity.

## Decision boundary

Ask the user before:

- broadening or narrowing who may see or mutate records;
- changing a `403` versus `404` non-disclosure policy;
- making a role global rather than project/site/Lab scoped;
- moving domain rules into authorization;
- restoring Redis as an authorization dependency;
- changing upload, grading, verification, or referral workflow meaning.
