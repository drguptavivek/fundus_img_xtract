# AGENT INSTRUCTIONS

## MANDATORY: Use td for Task Management

You must run td usage --new-session at conversation start (or after /clear) to see current work.
Use td usage -q for subsequent reads.

## Project Overview

Medical imaging system for fundus image management with multi-disease grading (Glaucoma, DR, AMD), three-tier dual grading workflow, and dataset curation for AI training. Features: multi-source ingestion (ZIP/PDF/Excel), RBAC+ABAC access control, audit trails, PostgreSQL materialized views.

## Tech Stack

- **Stack**: Flask + SQLAlchemy, PostgreSQL 18, Redis, Bootstrap 5.3
- **Package Manager**: `uv` (**CRITICAL**: Always use `uv run` prefix, never bare `python`)
- **Port**: 5001
- **Tests**: pytest (unit), Playwright (E2E - stale)

### 🚨 Docker Permission Issues

**Problem**: Commands run inside Docker container create files owned by `root`, causing permission errors when editing from host.

**Solution**: Always run Docker commands with your user ID (`-u $(id -u):$(id -g)`) for uv run alembic. Other commands can be run directly

```bash
#  - Creates root-owned files:
$DC exec web uv run alembic revision --autogenerate -m "description"

# CORRECT - Creates files with your ownership:
$DC exec web uv run alembic revision --autogenerate -m "description"

# Fix existing root-owned files via Docker:
$DC exec -u root web chown -R $(id -u):$(id -g) /app/migrations/versions
```

**Common offenders**: `alembic revision`, `uv run pytest`, file creation scripts

## Essential Commands

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

# Create user
docker compose exec web uv run python -m scripts.create_user <username>
```

## Architecture

**Core files**: `app.py` (Flask factory), `models.py` (70+ SQLAlchemy models), `wsgi.py` (Gunicorn entry)

**Key blueprints**: auth (login, RBAC), admin, analytics, grading (dual grading workflow), tasks, direct_uploads, remedio_zip_uploads, verify_remedio_*, review, search, api

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
- Small, focused commits with descriptive messages
- Do not duplicate code. Create reusable utilities and functions.  

## Key Files
**Config**: `pyproject.toml`, `alembic.ini`, `gunicorn_config.py`, `deploy.*.env`
**Utils**: `utils/utils.py` (@with_session), `utils/log_sanitize.py`, `utils/datetime_filters.py`
**Docs**: `docs/10-DEVELOP/CONVENTIONS.md`, `docs/10-DEVELOP/Security.md`, `docs/00-Core/models.md`, `instructions.md`

## 🚨 SESSION CLOSE PROTOCOL 🚨

**CRITICAL**: Before saying "done", MUST complete:
```bash
git status                    # Check changes
git add <files>              # Stage code
bd sync                      # Sync beads
git commit -m "message"      # Commit
bd sync                      # Sync beads again
git push                     # PUSH (work NOT done until this succeeds)
```

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

---

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

# 2. Commit and push code
git add . && git commit -m "Feature: description" && git push

# 3. Close bead (source of truth)
bd close <id>

# 4. Close GitHub issue
gh issue close <number> --comment "Completed via beads-<id>"

# 5. Sync beads
bd sync
```

**Deliverable**: Closed bead, closed GitHub issue, pushed code

---

### Quick Reference: When to Use This Workflow

| Scenario | Use Full Workflow? |
|----------|-------------------|
| New feature | ✅ Yes |
| Refactoring | ✅ Yes |
| New session | ✅ Yes |
| Simple bug fix (1-2 lines) | ⚠️ Skip to BEAD |
| Documentation only | ⚠️ Skip to BEAD |
| Trivial typo fix | ⚠️ Skip BEAD & TDD |

---

## Beads Workflow

### Valid Issue Types

**🚨 IMPORTANT**: The beads tool has **hardcoded valid issue types**. You cannot create custom types.

| Valid Types | Usage |
|-------------|-------|
| `bug` | Bug reports, security vulnerabilities, defects |
| `feature` | New features, enhancements |
| `task` | Tasks, chores, refactoring |
| `epic` | Large features spanning multiple issues |
| `chore` | Maintenance tasks, dependencies |
| `merge-request` | Git merge requests |
| `molecule` | Multi-issue coordination (swarm, patrol) |
| `gate` | Async coordination gates |
| `agent` | Agent-related issues |
| `role` | Agent role definitions |
| `rig` | Beads rig configuration |
| `convoy` | Multi-rig coordination |
| `event` | Event tracking |

**For security-related issues**: Use `type: "bug"` with `label: "security"` - do NOT attempt to use `type: "security"` as it will cause sync errors.

```bash
# CORRECT - Security bug with proper type and label
bd create --title="Fix XSS vulnerability" --type=bug --priority=1 --labels=security

# WRONG - Will cause sync errors (invalid type)
bd create --title="Fix XSS vulnerability" --type=security --priority=1
```

---

### Core Commands

**Create**: `bd create --title="..." --type=task|bug|feature --priority=2` (0=critical, 2=medium, 4=backlog)
**Start work**: `bd ready` → `bd show <id>` → `bd update <id> --status=in_progress`
**Update**: **CRITICAL** - Always update beads with implementation and verification details using `bd update <id> --description="..."`:
  - **Implementation section**: What was built/changed (files, features, configs)
  - **Verification section**: How it was tested (test results, commands run, validation)
  - Use Markdown format with clear headings
  - Include specific file paths, test counts, command outputs
  - Example format:
    ```markdown
    ## Implementation
    - Created X files: file1.py, file2.py
    - Updated Y with Z features
    - Config changes: ...

    ## Verification
    - Tests: X/Y passed
    - Manual verification: ...
    - Commands run: ...
    - Docker web Container has not errors:

    ## GIT Commit Deatils
     - Date, Time:
     - Commit ID:
     - Files Modified:
    ```
**Complete**: `bd close <id1> <id2> ...` → `bd sync`
**Dependencies**: `bd dep add <issue> <depends-on>`
**Rules**: Track multi-session/strategic work in beads. Use TodoWrite for single-session execution. Always add detailed descriptions (Markdown) and create corresponding GitHub issues with `gh issue create`.

## Beads ↔ GitHub Sync

### ⚠️ Beads is the PRIMARY Source of Truth

**Golden Rule**: If a Bead exists, GitHub issue is derived from it. Always update from Bead → GitHub, never the reverse.

---

### BD Troubleshooting

**Symptom**: `bd create` fails with permission errors for `/home/eyeimg/.beads-planning/.beads/beads.db`  
**Fix**: Force bd to use the repo-local DB in `.beads/beads.db`:

```bash
bd --no-daemon --db /home/eyeimg/fundus_img_xtract/.beads/beads.db create \
  --repo /home/eyeimg/fundus_img_xtract \
  --title="..." --type=feature --priority=2 \
  --description="..."
```

**Notes**:
- `bd where` should show the active repo path and DB location.
- If `bd` is not on PATH, use the full path or add it in `.bashrc`.

---

### Creation Workflow (Beads-First)

**Standard workflow - always create Bead first:**

```bash
# 1. Create the bead (source of truth)
bd create --title="Fix login bug" --type=bug --priority=1

# 2. Get the bead ID (e.g., beads-abc)
bd show beads-abc

# 3. Create corresponding GitHub issue (bead code at end of title)
gh issue create \
  --title "Fix login bug [bead-abc]" \
  --label "p1,Bug" \
  --body "Beads tracker: beads-abc"
```

**If GitHub issue exists first (rare edge case):**

```bash
# 1. Create corresponding bead to establish source of truth
bd create --title="Fix login bug" --type=bug --priority=1

# 2. Update GitHub title to include bead code
gh issue edit 123 --title "Fix login bug [bead-abc]"
```

---

### Closure Workflow (Beads-First)

**Always close Bead first, then GitHub:**

```bash
# 1. Complete the work, commit, push code
git add . && git commit -m "Fix login bug" && git push

# 2. Close the Bead (source of truth)
bd close beads-abc

# 3. Close the GitHub issue (derived from bead)
gh issue close 123 --comment "Fixed via beads-abc. Commit: <sha>"
```

**Batch closing multiple beads:**

```bash
# 1. Close beads (source of truth)
bd close beads-abc beads-def beads-xyz

# 2. Close corresponding GitHub issues
gh issue close 123 124 125 --comment "Completed via beads. Commit: <sha>"
```

---

### Status Change Sync (Beads-First)

| Beads Command (Source) | GitHub Action (Derived) |
|---------------|---------------|
| `bd update <id> --status=in_progress` | Add comment: "Started work on beads-<id>" |
| `bd close <id>` | `gh issue close <number>` |
| `bd reopen <id>` | `gh issue reopen <number>` |
| `bd update <id> --description="..."` | Add comment with summary |

---

### Quick Reference: Label Mapping

| Beads Priority | GitHub Label |
|----------------|--------------|
| `--priority=0` | `p0` |
| `--priority=1` | `p1` |
| `--priority=2` | `p2` |
| `--priority=3` | `p3` |
| `--priority=4` | `p4` |

| Beads Type | GitHub Label |
|------------|--------------|
| `--type=bug` | `Bug` |
| `--type=feature` | `Enhancement` |
| `--type=task` | `Task` |
| `--type=chore` | `Chore` |
| `--type=epic` | `Epic` |

---

### Verification Checklist

After creating work:
- [ ] Bead exists (`bd show <id>`)
- [ ] GitHub issue exists with matching title (includes `[bead-<id>]` at end)
- [ ] Priority label matches (p0-p4)
- [ ] Type label matches (Bug/Enhancement/Tests/Documentation/Duplicate/Wontfix/Dependencies/Chore/Task/Epic)

After closing work:
- [ ] Bead is closed (`bd show <id>` shows closed)
- [ ] GitHub issue is closed
- [ ] Commit pushed to remote
- [ ] `bd sync` run successfully

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

---

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
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

<!-- bv-agent-instructions-v1 -->

---

## Beads Workflow Integration

This project uses [beads_viewer](https://github.com/Dicklesworthstone/beads_viewer) for issue tracking. Issues are stored in `.beads/` and tracked in git.

### Essential Commands

```bash
# View issues (launches TUI - avoid in automated sessions)
bv

# CLI commands for agents (use these instead)
bd ready              # Show issues ready to work (no blockers)
bd list --status=open # All open issues
bd show <id>          # Full issue details with dependencies
bd create --title="..." --type=task --priority=2
bd update <id> --status=in_progress
bd close <id> --reason="Completed"
bd close <id1> <id2>  # Close multiple issues at once
bd sync               # Commit and push changes
```

### Workflow Pattern

1. **Start**: Run `bd ready` to find actionable work
2. **Claim**: Use `bd update <id> --status=in_progress`
3. **Work**: Implement the task
4. **Complete**: Use `bd close <id>`
5. **Sync**: Always run `bd sync` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `bd ready` shows only unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers, not words)
- **Types**: task, bug, feature, epic, question, docs
- **Blocking**: `bd dep add <issue> <depends-on>` to add dependencies

### Session Protocol

**Before ending any session, run this checklist:**

```bash
git status              # Check what changed
git add <files>         # Stage code changes
bd sync                 # Commit beads changes
git commit -m "..."     # Commit code
bd sync                 # Commit any new beads changes
git push                # Push to remote
```

### Best Practices

- Check `bd ready` at session start to find available work
- Update status as you work (in_progress → closed)
- Create new issues with `bd create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always `bd sync` before ending session

<!-- end-bv-agent-instructions -->
