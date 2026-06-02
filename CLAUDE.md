# AGENT INSTRUCTIONS

## Project

Fundus image management system for multi-disease grading (DR, glaucoma, AMD), dual/three-tier grading, ingestion, dataset curation, RBAC/ABAC access control, audit trails, PostgreSQL materialized views.

Stack: Flask, SQLAlchemy, PostgreSQL 18, Redis, Bootstrap 5.3, Celery Beat/Worker.

## Non-Negotiables

- Use `uv run`; never run bare `python`.
- Port is `5001`.
- Prefer `make` targets for routine work: `make up`, `make test`, `make logs-web`, `make logs-celery`, `make alembic-current`, `make alembic-upgrade`.
- For Docker commands that create files, especially Alembic revisions and pytest-generated files, run with host UID/GID:
  `docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run ...`
- Tests that use the PostgreSQL `test-db` service must run from inside the Compose network. Do not run host-side `uv run pytest` for DB tests that point at `test-db`, because the service hostname may not resolve from the host/sandbox even when the container is healthy. Use:
  `docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest <path-or-selection>`
- Do not commit after every small change. Commit only after implementation and verification are complete.
- Do not commit documentation-only changes unless explicitly requested or bundled with completed verified implementation work.

## Security And Data Rules

- All forms/AJAX need CSRF tokens: `{{ csrf_field() }}` or `X-CSRFToken`.
- Templates or HTMX partials that can be rendered directly must import their own CSRF macro with `{% from "_forms.html" import csrf_field %}`; do not rely on `base.html` imports for standalone partial renders.
- When moving forms into partials, verify both the full page render and the partial render path so `csrf_field` remains defined.
- All routes are protected by default except login; use `@roles_required(...)` and scope by lab units.
- Use parameterized queries only. Never build SQL with string concatenation.
- Sanitize user-controlled values in logs with `sanitize_log_value()`.
- Use `auth.security.hash_password()` and `verify_password()` for passwords.
- Use timezone-aware UTC datetimes via `auth.utils.utcnow()`.
- Display datetimes with the user timezone filters, for example `{{ value | user_datetime }}`.

## Database

- Never create ad-hoc sessions manually.
- Prefer the project DB helpers: `@with_session()` from `utils.utils`, `transaction_scope()` from `db_transaction_manager`, or `@transactional()` from `utils.db_transaction`.
- Keep transactions short and explicit. Let context managers commit/rollback.
- Avoid N+1 queries with `selectinload`/`joinedload`.
- Use Flask-Caching for expensive reusable reads, and invalidate caches when underlying data changes.

## API And UI

- Expose all new or materially changed functionality through explicit RESTful JSON APIs for mobile apps, JavaScript apps, and HTMX-driven frontend workflows unless the behavior is strictly internal server rendering.
- Frontend mutations and dynamic reads should call documented API endpoints from the `api` package. HTMX requests must include CSRF via `X-CSRFToken` or form-rendered `{{ csrf_field() }}`.
- Page routes should render initial pages, layouts, and reusable HTMX fragments only. They should not own JSON/data mutations or reusable application behavior.
- For HTMX mutations that affect select options, modal forms, counts, badges, or related lists, swap a shared workspace/container that includes every dependent fragment. Do not refresh only the visible table/panel if hidden modal or dropdown data can become stale.
- Keep HTMX modal/forms in reusable partials and return the same partial tree after mutations so dependent data is refetched from the server source of truth.
- All new API endpoints must live in the `api` package and register on `api_bp` from `api/__init__.py`, or on a versioned API blueprint such as `api/mobile/__init__.py`.
- Do not add `/api/...` routes inside page feature blueprints.
- API routes may return JSON by default and HTMX partials only when explicitly documented for progressive enhancement; keep the underlying domain/service contract DTO-based and reusable.
- Document request/response shape, auth/role requirements, lab/project scoping, validation errors, CSRF requirements, HTMX response behavior where applicable, and example calls.
- Generate API documentation under `docs/API/<feature-or-module>/` for each API surface; keep endpoint docs feature-scoped instead of scattering API details across unrelated docs.
- When modifying an existing `/api/...` route outside `api`, move it into the API blueprint when feasible.
- Use Bootstrap 5.3 and flash toasts for UI feedback.
- Add menu links in `templates/base.html` for new user-facing pages when appropriate.

## Migrations

- Always write real `upgrade()` and `downgrade()` logic. Never leave `pass`.
- Make migrations idempotent: check for existing tables, columns, indexes, constraints before creating or dropping.
- Use `--autogenerate` only as a starting point; review and remove unrelated autogenerated changes.
- Generate migrations with host UID/GID, for example:
  `docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run alembic revision --autogenerate -m "description"`
- Check migration state with `make alembic-heads`, `make alembic-current`, and run with `make alembic-upgrade`.

## Architecture

- Keep Flask routes thin: authenticate/authorize, parse and validate transport input, call service module functions, then render/redirect/return JSON. Do not put business rules, query construction, or workflow branching in routes.
- Put domain rules, scoping, validation, query composition, DTOs, serializers/deserializers, and typed exceptions in cohesive deep service modules with narrow public interfaces.
- Organize deep feature modules as folders that own their ORM models, service logic, DTOs, serializers, validators, and domain exceptions. Avoid scattering a feature's domain code across unrelated top-level files. Web APIs, page routes/blueprints, and Jinja templates may remain in the shared `api/`, route/blueprint, and `templates/` directories while delegating domain behavior to the deep module.
- Treat DTOs as the contract between routes, APIs, templates, and services. Avoid passing raw request data, ORM rows, or ad-hoc dicts across module boundaries when a typed DTO or serializer is appropriate.
- Build features around service modules that can serve JSON APIs, HTMX partials, background jobs, and tests from the same domain layer.
- Do not duplicate permission checks, scope expansion, filtering, or grading business rules across routes/templates.
- Keep compatibility shims only temporarily; remove them once callers are migrated.
- Do not duplicate code. Create reusable utilities where the codebase already has a matching pattern.

## Key Workflows

- Dual grading: Resident -> Resident2 -> Arbitrator when disagreement. See `docs/04-Grade/comprehensive_dual_grading_system.md`.
- Image ingestion: Remedio ZIP/PDF OCR -> verification -> tasks; direct uploads get UUIDs and manual tasks; Excel imports create review tasks.
- Materialized views: `mv_encounter_pivot_dr`, `mv_encounter_pivot_glaucoma`, `mv_encounter_pivot_amd`, `mv_direct_image_pivot`; refresh with `refresh_all_materialized_views(db)`.

## Docs

- Update relevant docs under `docs/` when module behavior, workflows, or public interfaces materially change.
- Update the docs index in `README.md` when adding, moving, or materially changing docs.
- Key references: `docs/10-DEVELOP/DB CONTEXT MANAGER.md`, `docs/10-DEVELOP/Security.md`, `docs/00-Core/models.md`, `instructions.md`.

## Beads And Closeout

- For new features, refactors, or non-trivial bugs: plan, create/update a bead, implement with tests, verify, update/close the bead.
- Minimal commands:
  `bd ready`
  `bd create --title="..." --type=task|bug|feature --priority=2`
  `bd update <id> --status=in_progress`
  `bd update <id> --description="## Implementation\n...\n## Verification\n..."`
  `bd close <id>`
  `bd vc status`
  `bd export -o .beads/issues.jsonl`
- This repository uses Beads `bd` with Dolt in embedded mode. Confirm with `.beads/metadata.json` (`"dolt_mode": "embedded"`) and `bd version`.
- Do not use `bd sync`, `bd dolt push`, or server-mode Dolt commands for normal workflow in this repo.
- Keep Beads state in Git by including the tracked files `.beads/config.yaml`, `.beads/metadata.json`, and `.beads/issues.jsonl`. Runtime directories such as `.beads/dolt/`, `.beads/embeddeddolt/`, `.beads/backup/`, logs, locks, and export-state files remain ignored.
- After creating/updating/closing beads, run `bd export -o .beads/issues.jsonl`, then review and commit the resulting `.beads/issues.jsonl` change with the implementation when appropriate.
- If embedded Dolt state is missing but `.beads/issues.jsonl` exists, rebuild with:
  `bd init --force --destroy-token DESTROY-fundus_img_xtract --database beads --from-jsonl --skip-agents --skip-hooks`

## Common Files

- Config: `pyproject.toml`, `alembic.ini`, `gunicorn_config.py`, `deploy.*.env`
- Core app: `app.py`, `models.py`, `api/`, `auth/`, `grading/`, `review/`, `analytics/`, `datasets/`
- Utilities: `utils/utils.py`, `utils/log_sanitize.py`, `utils/datetime_filters.py`, `db_transaction_manager.py`
- Templates/static: `templates/`, `static/`

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking in embedded Dolt mode. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
bd export -o .beads/issues.jsonl  # Write tracked issue export
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files
- Do not use `bd sync` or `bd dolt push`; this repo uses embedded Dolt plus the tracked `.beads/issues.jsonl` export

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd export -o .beads/issues.jsonl
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
