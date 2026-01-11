# AGENT INSTRUCTIONS

## Project Overview

Medical imaging system for fundus image management with multi-disease grading (Glaucoma, DR, AMD), three-tier dual grading workflow, and dataset curation for AI training. Features: multi-source ingestion (ZIP/PDF/Excel), RBAC+ABAC access control, audit trails, PostgreSQL materialized views.

## Tech Stack

- **Stack**: Flask + SQLAlchemy, PostgreSQL 18, Redis, Bootstrap 5.3
- **Package Manager**: `uv` (**CRITICAL**: Always use `uv run` prefix, never bare `python`)
- **Port**: 5001
- **Tests**: pytest (unit), Playwright (E2E - stale)

### 🚨 Docker Permission Issues

**Problem**: Commands run inside Docker container create files owned by `root`, causing permission errors when editing from host.

**Solution**: Always run Docker commands with your user ID (`-u $(id -u):$(id -g)`):

```bash
# WRONG - Creates root-owned files:
$DC exec web uv run alembic revision --autogenerate -m "description"

# CORRECT - Creates files with your ownership:
$DC exec -u $(id -u):$(id -g) web uv run alembic revision --autogenerate -m "description"

# Fix existing root-owned files via Docker:
$DC exec -u root web chown -R $(id -u):$(id -g) /app/migrations/versions
```

**Common offenders**: `alembic revision`, `uv run pytest`, file creation scripts

## Essential Commands

```bash
# Docker compose prefix (use for all commands below)
DC="docker compose --env-file deploy.config.env --env-file deploy.secrets.env"

# Start services
$DC up web -d

# Run tests
$DC exec web uv run pytest tests/

# Database migrations (NOTE: use -u flag to avoid root-owned files)
$DC exec web uv run alembic heads
$DC exec -u $(id -u):$(id -g) web uv run alembic revision --autogenerate -m "description"
$DC exec web uv run alembic upgrade head

# Create user
$DC exec web uv run python -m scripts.create_user <username>
```

## Architecture

**Core files**: `app.py` (Flask factory), `models.py` (70+ SQLAlchemy models), `wsgi.py` (Gunicorn entry)

**Key blueprints**: auth (login, RBAC), admin, analytics, grading (dual grading workflow), tasks, direct_uploads, remedio_zip_uploads, verify_remedio_*, review, search, api

## MANDATORY Patterns

### 1. Database Sessions
Always use `@with_session()` decorator (never create sessions manually):
```python
from utils.utils import with_session

@with_session()
def my_function(db):
    user = db.query(User).filter_by(username='admin').first()
    return user  # Auto-commit/rollback/close
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

## Beads Workflow
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

**Automatic Sync**: Beads are automatically synced with GitHub issues every 30 minutes via cron.

### Sync Scripts
```bash
# One-time: Create all GitHub labels
./scripts/setup_bead_labels.sh

# Manual: Force sync beads with GitHub issues
./scripts/sync_beads_to_github.sh

# View sync logs
cat .beads/bead_sync.log
```

### How It Works
- **Sync Interval**: Every 30 minutes via cron
- **Caching**: Only tracks open issues locally (`.beads/open_issues_cache.txt`)
- **Rate Limit Protection**: Only checks cached open beads (not all 48 issues)
- **Daily Full Check**: Once per day, checks for newly opened beads & refreshes mapping
- **Idempotent**: Only acts when state differs

### When Adding New Beads

After creating a new bead and its GitHub issue, the sync is **fully automatic**:

1. Create the GitHub issue (include `## Bead Reference: fundus_img_xtract-XXX` in body)
2. Run `./scripts/setup_bead_labels.sh` to create the bead label (one-time)
3. Done! The sync script auto-discovers the mapping daily

**No manual mapping needed** - The sync script parses GitHub issue bodies to extract bead IDs and builds the mapping automatically.

### Bead-to-Issue Mapping (Current: 48 beads)

| ID | Issue | Title | Priority |
|----|-------|-------|----------|
| 9rb | #22 | Enhance Test Fixtures for Hospital Isolation | P0 |
| ugh | #23 | Add Login and Session Fixtures | P2 |
| 5pi | #24 | Add Test User Fixtures to conftest.py | P2 |
| s8t | #25 | Phase 2: Move Unit Tests | P2 |
| snk | #26 | Phase 1: Test Infrastructure Setup | P2 |
| toj | #4 | Phase 3A: Update Existing API Endpoints | P0 |
| awm | #5 | Phase 2: Fix Remaining Hospital Scoping Tests | P0 |
| duv | #6 | Phase 2: Hospital Scoping Utilities | P0 |
| 4s9 | #10 | Phase 3B: Add New Hospital Context APIs | P1 |
| b3g | #7 | Backfill Existing Users with Hospital Assignment | P1 |
| 8r1 | #8 | Phase 4A: Update Image & Task Queries | P1 |
| b05 | #9 | Phase 3C: Update JavaScript Files | P1 |
| 4uu | #11 | Phase 3: Query Updates | P1 |
| 49p | #12 | Add Hospital Scoping Integration Tests | P2 |
| d1h | #13 | Security Audit: Verify All Routes Have Hospital Scoping | P2 |
| 62a | #14 | Phase 5B: Implement 2-Week Cooling-Off | P2 |
| crn | #15 | Phase 5A: Implement Optometrist PII Anonymization Workflow | P2 |
| y7z | #16 | Phase 4B: Add New Roles | P2 |
| ubr | #17 | Phase 6: Cleanup and Documentation | P2 |
| jms | #18 | Phase 5: Create Specialized Test Suites | P2 |
| mzt | #19 | Phase 4: Reorganize E2E Tests | P2 |
| j9p | #20 | Phase 3: Move Integration Tests | P2 |
| d18 | #21 | Phase 6: Documentation, E2E Tests & Deployment | P3 |
| 8g7 | #27 | Code Quality & SonarQube Fixes | P2 |
| 3do | #28 | Phase 5A: Grading API PII Sanitization | P0 |
| r4o | #29 | 5O: PII Masking Utility | P1 |
| tvp | #30 | 5N-5: Integrate Re-Auth with Admin Exports | P1 |
| 43u | #31 | 5N-2: Re-Authentication Decorator | P1 |
| 1yu | #32 | 5N-1: SensitiveOperationAudit Model | P1 |
| tig | #33 | 5M: Admin Export Audit & Controls | P1 |
| f6n | #34 | 5K: Export Pipeline Sanitization | P1 |
| dcl | #35 | 5H: KPI & Export Sanitization | P1 |
| jx8 | #36 | 5B: Optometrist Anonymization Workflow | P1 |
| 4g2 | #37 | 5A: Grading API Sanitization | P1 |
| c2i | #38 | 5N-6: Sensitive Operations Dashboard | P2 |
| cwi | #39 | 5N-4: Re-Auth Confirmation Template | P2 |
| o25 | #40 | 5N-3: Encrypted Export Utility | P2 |
| las | #41 | 5L: Filename Anonymization | P2 |
| det | #42 | 5I: Screenings Hospital Verification | P2 |
| 55n | #43 | 5G: Jobs & Review Audit | P2 |
| 51f | #44 | 5F: Analytics Anonymization | P2 |
| sy5 | #45 | 5E: Search & Utils Sanitization | P2 |
| ej1 | #46 | 5D: Logging Audit | P2 |
| e3j | #47 | 5C: UI Template Defense | P2 |
| 57m | #48 | 5J: Image Metadata Stripping | P3 |

---