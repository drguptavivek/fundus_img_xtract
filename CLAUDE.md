# AGENT INSTRUCTIONS

## Project Overview

Medical imaging system for fundus image management with multi-disease grading (Glaucoma, DR, AMD), three-tier dual grading workflow, and dataset curation for AI training. Features: multi-source ingestion (ZIP/PDF/Excel), RBAC+ABAC access control, audit trails, PostgreSQL materialized views.

## Tech Stack

- **Stack**: Flask + SQLAlchemy, PostgreSQL 18, Redis, Bootstrap 5.3, Celery Beat, Celery Worker
- **Package Manager**: `uv` (**CRITICAL**: Always use `uv run` prefix, never bare `python`)
- **Port**: 5001
- **Tests**: pytest (unit), Playwright (E2E - stale)

### 🚨 Docker Permission Issues

**Problem**: Commands run inside Docker container create files owned by `root`, causing permission errors when editing from host.
**Solution**: Always run Docker commands with your user ID (`-u $(id -u):$(id -g)`) for uv run alembic. Other commands can be run directly
**Common offenders**: `alembic revision`, `uv run pytest`, file creation scripts

## Essential Commands

Use `make` for common operations such as `logs`, `logs-tail`, `logs-web`, `logs-web-tail`, `logs-celery`, `logs-celery-tail`, `logs-workers`, `logs-workers-tail`, `logs-db`, `logs-db-tail`, `alembic-current`, `start`, `stop`, `restart`, `restart-all`, `restart-celery`, `backup`, `test`, `script`/`scripts`, and `shell`; only `*-tail` log targets follow logs.

```bash
# Docker compose prefix (use for all commands below)
DC="docker compose "

# Start services
$DC up web -d

# Run tests
$DC exec web uv run pytest tests/

# Database migrations (NOTE: use -u flag to avoid root-owned files)
docker compose exec web uv run alembic heads
docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run alembic revision  --autogenerate -m  "description"
docker compose exec web uv run alembic upgrade head

```
## MANDATORY Patterns

### 1. Database Sessions
Always use  db conmtext manager  (never create sessions manually):

**Preferred Method**: Use context managers from `utils.utils`
see `docs/10-DEVELOP/DB CONTEXT MANAGER.md`

    - Example:
        ```python
        from db_transaction_manager import transaction_scope
        
        @bp.route('/submit-grade', methods=['POST'])
        @login_required
        def submit_grade():
            # Get form data
            grade_data = request.form
            
            with transaction_scope() as db:
                try:
                    # Call utility function, passing the database session
                    result = process_grade_submission(db, grade_data, current_user.id)
                    flash('Grade submitted successfully', 'success')
                    return redirect(url_for('grading.index'))
                except Exception as e:
                    flash(f'Error submitting grade: {str(e)}', 'error')
                    # Transaction automatically rolled back
        ```
      
       

### 2. CSRF Protection
All forms/AJAX must include CSRF tokens:
```html
<form method="POST">{{ csrf_field() }}</form>
```
```javascript
headers: {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content}
```

### 3. Datetime Handling
Always use UTC timezone-aware datetimes:
```python
from auth.utils import utcnow
task.created_at = utcnow()  # Store in DB
```
```html
{{ task.created_at | user_datetime }}  <!-- Display to user -->
```

### 4. Logging
Sanitize all user input in logs:
```python
from utils.log_sanitize import sanitize_log_value
logger = logging.getLogger('dual_grading')  # or security, database, etc.
logger.info("User %s action", sanitize_log_value(username))
```

### 5. Access Control
All routes protected by default (except `/login`). Use `@roles_required()` and scope by lab_units:
```python
from auth.roles import roles_required

@roles_required("admin", "data_manager")
def admin_function():
    eligible_labs = [u.id for u in current_user.lab_units]
    tasks = db.query(GradingTask).filter(GradingTask.lab_unit_id.in_(eligible_labs))
```

### 6. Database Transaction Manager
For complex multi-step operations requiring transactional control, use the transaction manager:
```python
from utils.db_transaction import transactional

@transactional()
def complex_update(user_id, changes):
    # All operations in this function are atomic
    # Auto-commit on success, auto-rollback on exception
    user = db.query(User).get(user_id)
    user.update(changes)
    create_audit_log(user_id, changes)
    send_notification(user_id)  # Only runs if DB operations succeed
```

### 7. Flask Caching
Use Flask-Caching for expensive operations (query results, computations):
```python
from flask_caching import cache

@cache.memoize(timeout=300)  # Cache for 5 minutes
def expensive_query(lab_id):
    return db.query(GradingTask).filter_by(lab_unit_id=lab_id).all()

# Clear cache when data changes
def update_grading_task(task_id, changes):
    task = db.query(GradingTask).get(task_id)
    task.update(changes)
    cache.delete_memoized(expensive_query, task.lab_unit_id)
```

### 8. Alembic Migrations (CRITICAL)

**🚨 NEVER use `pass` in migrations** - always write proper upgrade/downgrade.
**🚨 Make migrations IDEMPOTENT** - they should be safe to run multiple times:

```bash
# Generate migration (use -u flag to avoid root-owned files)
$DC exec  web uv run alembic revision --autogenerate -m "description"

# Review the generated migration file
# CHECK aNd EDIT CONTENTS> Remove extra lines. Idempotency ensured
$DC exec web uv run alembic heads  # Check current head
$DC exec web uv run alembic history  # Review sequence
```

**Always review and edit the migration file:**

```python
# BAD - Never do this:
def upgrade():
    pass

# GOOD - Proper, idempotent migration:
def upgrade():
    # Check if exists before creating (idempotent)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'new_table') THEN
                CREATE TABLE new_table (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    user_id INTEGER REFERENCES users(id)
                );
            END IF;
        END $$;
    """)

    # Check if column exists before adding (idempotent)
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]
    if 'new_field' not in columns:
        op.add_column('users', sa.Column('new_field', sa.String(50), server_default='default'))

    # Check if index exists before creating (idempotent)
    if not op.get_context().dialect.has_index(conn, 'users', 'ix_users_new_field'):
        op.create_index('ix_users_new_field', 'users', ['new_field'])

def downgrade():
    op.drop_index('ix_users_new_field', table_name='users')
    op.drop_column('users', 'new_field')
    op.drop_table('new_table')
```

**Migration rules:**
- Always write both `upgrade()` and `downgrade()`
- Make migrations **idempotent** - safe to re-run if needed
- Use `op.execute()` with PostgreSQL `IF NOT EXISTS` checks
- Check for existing objects before creating them
- Use `--autogenerate` as a starting point, then edit
- Clean up autogenerated file as it may have many many extraneous queries
- Ensure migration is idempotent
- Test migrations on staging first
- Never skip migration work with `pass`

## Key Workflows

**Dual Grading**: Resident → Resident2 → Arbitrator (if disagree). See `docs/04-Grade/comprehensive_dual_grading_system.md`. Key utils: `dualGradingFetchDetailUtils`, `dualGradingEligibility`, `dualGradingConsensusUtils`.

**Image Ingestion**: ZIP (Remedio FOP + PDF OCR) → verification → auto-task creation. Direct uploads: immediate UUID + manual tasks. Excel import: pre-graded data → review tasks.

**Materialized Views**: 4 pivot views (`mv_encounter_pivot_dr/glaucoma/amd`, `mv_direct_image_pivot`) refresh every 30min. Manual: `refresh_all_materialized_views(db)`.

## Security Checklist (MANDATORY)
- CSRF tokens on ALL forms/AJAX
- Parameterized queries (never string concatenation)
- `@roles_required()` on routes
- `sanitize_log_value()` for user input in logs
- `auth.security.hash_password()` / `verify_password()` for passwords
- Validate all user input

## Code Standards
- PEP 8, PEP 484 type hints, docstrings
- Use `@with_session()` for DB (never manual sessions)
- Efficient queries (selectinload/joinedload, avoid N+1)
- Bootstrap 5.3 for UI, flash toasts for feedback
- Commit only after the work scope is complete and verified; do not commit after each small change
- Do not commit documentation-only changes unless explicitly requested or bundled into a completed, verified work session
- Do not duplicate code. Create reusable utilities and functions.  

## Architecture Pattern: Deep Modules, Thin Interfaces

For cross-cutting domain logic, prefer a dedicated deep module with a narrow public interface instead of spreading logic across routes, templates, and ad-hoc utilities.

**Recommended pattern:**
- Put domain rules, scoping, validation, query composition, DTOs, and typed exceptions in one cohesive module.
- Expose a small set of route-facing functions with clear names and stable return types.
- Keep Flask routes thin: parse request, call the domain interface, persist/render/redirect.
- Do not let routes duplicate permission checks, scope expansion rules, or filtering logic.
- During migrations, keep old utility modules only as thin compatibility shims that delegate to the new module.
- Once callers are migrated, remove the shim to avoid split-brain business logic.

**Example:** Upload scoping should live in a dedicated module such as `utils/upload_scope.py`. Existing `utils/upload_eligibility.py` should be merged into that module or temporarily reduced to a compatibility shim that re-exports/delegates to `upload_scope.py`.

## Key Files
**Config**: `pyproject.toml`, `alembic.ini`, `gunicorn_config.py`, `deploy.*.env`
**Utils**: `utils/utils.py` (@with_session), `utils/log_sanitize.py`, `utils/datetime_filters.py`
**Docs**: `docs/10-DEVELOP/CONVENTIONS.md`, `docs/10-DEVELOP/Security.md`, `docs/00-Core/models.md`, `instructions.md`

## 🚨 SESSION CLOSE PROTOCOL 🚨

**Commit timing rules:**
- Do not commit after every small change; batch related edits into one intentional commit after implementation and verification are complete.
- Do not commit documentation-only changes unless the user explicitly asks for a commit/push, or the doc change is part of a completed verified implementation session.
- It is acceptable to leave documentation-only work unstaged/uncommitted and report the changed files in the handoff.

## Development Workflow

### For New Features, Refactoring, or Starting New Sessions

**MANDATORY SEQUENCE**: Plan → Discuss → Optimize → BEAD → TDD → Close

```
┌─────────┐    ┌──────────┐    ┌───────────┐    ┌──────┐    ┌─────┐    ┌───────┐
│  Plan   │ →  │ Discuss  │ →  │ Optimize  │ →  │ BEAD │ →  │ TDD │ →  │ Close │
└─────────┘    └──────────┘    └───────────┘    └──────┘    └─────┘    └───────┘
```

---

### 1. PLAN - Understand and Explore

**Goal**: Understand requirements, explore codebase, identify files

```bash
# Use Explore agent for codebase investigation
# Ask Claude to explore:
# - Existing patterns and conventions
# - Similar features already implemented
# - Relevant files and modules
# - Dependencies and integrations
```

**Deliverable**: Clear understanding of what needs to be built, where it fits

---

### 2. DISCUSS - Validate Approach

**Goal**: Confirm understanding, clarify ambiguities, agree on approach

- Use `AskUserQuestion` tool for key decisions
- Confirm architectural choices (e.g., "Use Redis vs in-memory cache?")
- Validate edge cases and error handling
- Agree on test strategy

**Deliverable**: Approved approach with no open questions

---

### 3. OPTIMIZE - Design Implementation

**Goal**: Design efficient solution before coding

- Identify reusables (don't duplicate code)
- Plan efficient queries (avoid N+1)
- Consider security implications (CSRF, input validation, RBAC)
- Design for testability

**Deliverable**: Implementation plan with file list and approach

---

### 4. BEAD - Create Tracker

**Goal**: Establish source of truth for the work

```bash
# Create bead AFTER planning is complete
bd create --title="Feature name" --type=feature --priority=2

# Create corresponding GitHub issue (bead code at end of title)
gh issue create --title "Feature name [bead-xyz]" --label "p2,Enhancement"
```

**Deliverable**: Bead and GitHub issue tracking the work

---

### 5. TDD - Test-Driven Development

**Goal**: Write tests first, then implementation

```bash
# 1. Write failing test
$DC exec -u $(id -u):$(id -g) web uv run pytest tests/test_feature.py -v

# 2. Write minimal code to pass test

# 3. Refactor while keeping tests green
$DC exec web uv run pytest tests/
```
**Deliverable**: Tested code with coverage

### 6. CLOSE - Complete the Cycle

**Goal**: Update bead, close GitHub issue, push code

```bash
# 1. Update bead with implementation details
bd update <id> --description="
## Implementation
- Created files: file1.py, file2.py
- Updated X with Y features

## Verification
- Tests: X/Y passed
- Commands run: pytest tests/
"

# 2. Commit and push code only after implementation and verification are complete
git add . && git commit -m "Feature: description" && git push

# 3. Close bead (source of truth)
bd close <id>

# 4. Close GitHub issue
gh issue close <number> --comment "Completed via beads-<id>"

# 5. Commit Beads/Dolt state
bd vc commit -m "Update beads state"
```

**Deliverable**: Closed bead, closed GitHub issue, pushed code

### Quick Reference: When to Use This Workflow

| Scenario | Use Full Workflow? |
|----------|-------------------|
| New feature | ✅ Yes |
| Refactoring | ✅ Yes |
| New session | ✅ Yes |
| Simple bug fix (1-2 lines) | ⚠️ Skip to BEAD |
| Documentation only | ⚠️ Skip to BEAD; do not auto-commit unless requested |
| Trivial typo fix | ⚠️ Skip BEAD & TDD |

---

## Beads Workflow

Use only the minimal Beads commands needed for this repo:

```bash
bd ready
bd show <id>
bd create --title="..." --type=task|bug|feature --priority=2
bd update <id> --status=in_progress
bd update <id> --description="## Implementation\n...\n## Verification\n..."
bd close <id>
bd vc status
bd vc commit -m "Update beads state"
```

Backend notes:
- `bd 0.62.0` uses Dolt as the active backend.
- Use `bd context`, `bd dolt status`, and `bd doctor` only for troubleshooting.
- If the Dolt database is missing but `.beads/issues.jsonl` exists, rebuild with:
  `bd init --force --destroy-token DESTROY-fundus_img_xtract --database beads --from-jsonl --skip-agents --skip-hooks`
- `bd sync` is obsolete in this version.

## GitHub Labels

### Priority Labels (use one)
| Label | Color | Description |
|-------|-------|-------------|
| `p0` | 🔴 b60205 | Priority P0 - Critical |
| `p1` | 🟠 ff9f1c | Priority P1 - High |
| `p2` | 🟡 ffcd56 | Priority P2 - Medium |
| `p3` | 🔷 C5DEF5 | Priority P3 - Low |
| `p4` | 🔷 1D76DB | Priority P4 - Backlog |

### Type Labels (use one)
| Label | Description |
|-------|-------------|
| `Bug` | Bug report |
| `Enhancement` | Feature request |
| `Tests` | Test related |
| `Documentation` | Docs changes |
| `Duplicate` | Duplicate issue |
| `Wontfix` | Won't fix |
| `Dependencies` | Dependency updates |
| `Chore` | Maintenance tasks |
| `Task` | Task item |
| `Epic` | Large multi-issue effort |
