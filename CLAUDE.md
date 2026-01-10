# CLAUDE.md

## Project Overview

Medical imaging system for fundus image management with multi-disease grading (Glaucoma, DR, AMD), three-tier dual grading workflow, and dataset curation for AI training. Features: multi-source ingestion (ZIP/PDF/Excel), RBAC+ABAC access control, audit trails, PostgreSQL materialized views.

## Tech Stack

- **Stack**: Flask + SQLAlchemy, PostgreSQL 18, Redis, Bootstrap 5.3
- **Package Manager**: `uv` (**CRITICAL**: Always use `uv run` prefix, never bare `python`)
- **Port**: 5001
- **Tests**: pytest (unit), Playwright (E2E - stale)

## Essential Commands

```bash
# Docker compose prefix (use for all commands below)
DC="docker compose --env-file deploy.config.env --env-file deploy.secrets.env"

# Start services
$DC up web -d

# Run tests
$DC exec web uv run pytest tests/

# Database migrations
$DC exec web uv run alembic heads          # Check for conflicts
$DC exec web uv run alembic revision --autogenerate -m "description"
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
**Complete**: `bd close <id1> <id2> ...` → `bd sync`
**Dependencies**: `bd dep add <issue> <depends-on>`
**Rules**: Track multi-session/strategic work in beads. Use TodoWrite for single-session execution. Always add detailed descriptions (Markdown) and create corresponding GitHub issues with `gh issue create`.

---