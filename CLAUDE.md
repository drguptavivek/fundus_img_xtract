# KiloCode Instructions for Fundus Image Manager

## Overview
This directory contains comprehensive instructions for KiloCode to work effectively with the Fundus Image Manager project.


## When working with code
1. use `uv run app.py` for development
2. use `uv run` to run commands 
3. DO MOT use python run, python compile, etc. Ass uses Virtual Environment in .venv
4. App uses port `http://127.0.0.1:5001` 
5. Login endpoint is /login
6. All routes are protected  except those listed in app.py:_require_login_everywhere
7. base.html JINJA  template exposes -   {% block extra_styles %},     {% block content %},   {% block page_scripts %}. It also imports     {% from "_forms.html" import csrf_field %}

## Key Workflows
1. **Image Upload**: Direct uploads or ZIP processing
2. **Dual Grading**: Resident → Resident2 → Arbitration
3. **AI Integration**: AI model grades alongside human graders
4. **Quality Assurance**: Consensus building and review

## Technical Stack
- **Backend**: Flask with SQLAlchemy
- **Frontend**: Bootstrap 5.3 with custom SCSS
- **Database**: SQLite/PostgreSQL
- **Package Manager**: uv for Python, npm for CSS
- **Testing**: pytest + Playwright

## Important Conventions

### Database Session Management
**Preferred Method**: Use context managers from `utils.utils`
see `docs/10-DEVELOP/DB CONTEXT MANAGER.md`

```python
from utils.utils import with_session

@with_session()
def my_function(db):
    # Use db session here
    user = db.get(User, user_id)
    # No need to commit/close - handled automatically
```

### Route Protection
**Role-based access control**:
```python
from auth.roles import roles_required

@bp.route("/admin")
@roles_required("admin", "data_manager")
def admin_view():
    # Only admins and data managers can access
```

### CSRF Protection
**Proper form pattern**:
Base.html already imports   csrf_field macro from   _forms.html
```html
<form method="POST">
    {{ csrf_field() }}
    <!-- form fields -->
</form>
```
 see `docs/10-DEVELOP/JavaScript_Guidance.md` for using CSRF in JS.




### Environment Variables
**Loading and usage pattern**:
```python
from utils.env_loader import load_environment, get_env
import os

load_environment()
secret_key = get_env("FLASK_SECRET_KEY", "default-value")
is_debug = str(get_env("DEBUG", "false")).lower() in ("1", "true", "yes")
```

## Getting Started

For KiloCode agents working on this project:

1. **First Time**: Read `comprehensive-instructions.md` completely

## Documentation References

This instruction set is based on and references:
- `docs/10-DEVELOP/CONVENTIONS.md` - Detailed development conventions
- `AGENTS.md` - Development guidelines and protocols
- `docs/Security.md` - Comprehensive security documentation
- `docs/Email.md` - Email functionality documentation
- `docs/10-DEVELOP/DateTime.md`
- [Datetime Filters](docs/10-DEVELOP/Utilities/utils_datetime_filters.md) - Jinja filters for timezone-aware datetime rendering
- [Timezone Choices](docs/10-DEVELOP/Utilities/utils_timezone_choices.md) - Helpers for timezone selection with human-readable labels
- [Flash Toasts Component](static/js/flash-toasts.md)




### 📋 [comprehensive-instructions.md](./comprehensive-instructions.md)

The comprehensive file is organized with clear sections:
- **Project Overview & Setup** - For getting started
- **Development Workflow & Best Practices** - For daily development
- **Mode-Specific Instructions** - For different KiloCode modes
- **Quick Reference** - For common patterns and commands
- **Security & Medical Data** - For compliance requirements


### 🔧 [mcp.json](./mcp.json)
MCP server configuration for Playwright integration.

# Fundus Image Manager
##  Technical Details
- **Backend:** Python, Flask
- **Database:** SQLAlchemy with PostgreSQL production support
- **Custom JS:** Flash-Toasts.js, photoswipe, edit_image.js, app.js, etc in /static/js
-  **CSS:**  Bootstrap 5.3 via SCSS. Overides in app.css
- **Alembic migrations:** 
  - Check for a single head before creating migrations: `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run alembic heads`.
  - If multiple heads exist, merge them first (e.g., `... exec web uv run alembic merge -m "merge heads" head1 head2`) then generate your migration from the unified head.
  - Generate with Alembic (not manually): `... exec web uv run alembic revision -m "message" --autogenerate`.
  - Apply with: `... exec web uv run alembic upgrade head`.
- **CSRF in JS:** include the token from `<meta name="csrf-token">` on AJAX calls via `X-CSRFToken` (see docs/10-DEVELOP/JavaScript_Guidance.md).
- **Reusable Partials:** -  _forms.html for CSRF, _viewer_card.html
- **Environment:**  .env and .env.example
- **Materialized Views:** Advanced analytics with disease-specific pivot views

##  Common Commands
### Development
- `uv run app.py` - Run the application
- `uv run` - Run commands with proper virtual environment
- `uv add` - Install packages (preferred over uv pip install)
- `npm run build:css` - Build Theme
- `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run alembic upgrade head` - Apply database migrations

### Database & Migrations
- `uv run alembic revision -m "description"` - Create new migration
- `uv run alembic upgrade head` - Apply migrations
- `uv run alembic downgrade -1` - Rollback one migration
- `uv run alembic current` - Show current revision

### Docker Development
- **Always use proper Docker exec:** `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run <command>`
- **Environment Loading:** Load both .env files: deploy.config.env and deploy.secrets.env

### Materialized Views
- `SELECT refresh_grading_data_view();` - Refresh general view
- `SELECT refresh_diabetic_retinopathy_grading_pivot();` - Refresh DR pivot
- `SELECT refresh_glaucoma_grading_pivot();` - Refresh glaucoma pivot
- `SELECT refresh_amd_grading_pivot();` - Refresh AMD pivot

### Production Deployment
- PORT 5001
- Use virtual environment .venv


## CODING PROTOCOL ##
**Coding Instructions**

### Development Workflow
- First understand the request and ask clarifying questions
- Explain your approach step-by-step before writing any code
- No unrelated edits - focus on just the task you're on
- Follow PEP 8 style guidelines
- Apply PEP 484 type annotations
- Proper memory management
- Always close db sessions
- Choose efficient query loading
- Use proper dependency injection
- Implement proper request validation
- Implement proper error handling and exceptions
- Use explicit error handling, no unwraps in production code
- Build Logic First, then build front-end template
- Use Secure Coding practices
- Ensure CSRF protection in all forms @templates/_forms.html
- Ensure SQL Injection security
- Add allowed roles for each route
- Use Flash toasts for user feedback
- Use available styles only
- Keep code modular using blueprints
- Include docstrings
- Organize templates in sub-folders
- Ensure no data is lost
- No sweeping changes
- Commit small, frequent changes for readable diff

### Database & Materialized Views
**Database Session Management:**
**Preferred Method:** Use context managers from `db_transaction_manager` (not `utils.utils`)
```python
from db_transaction_manager import transaction_scope

def my_function():
    with transaction_scope() as db:
        # Use db session here - automatically committed/closed
        user = db.get(User, user_id)
        result = db.execute(text("SELECT * FROM grades")).fetchall()
        # No explicit commit/rollback needed - handled automatically
```

**Error Handling with Transactions:**
```python
from db_transaction_manager import transaction_scope
from sqlalchemy import text

def update_grade_data():
    try:
        with transaction_scope() as db:
            # Multiple operations in single transaction
            db.execute(text("UPDATE grades SET status = 'reviewed' WHERE id = :id"), {"id": grade_id})
            db.execute(text("INSERT INTO audit_log (action) VALUES (:action)"), {"action": "grade_updated"})
            # Auto-commit on successful completion

    except Exception as e:
        # Auto-rollback on any exception
        logger.error(f"Failed to update grade: {e}")
        raise
```

**Materialized View Development:**
- Follow existing patterns in `utils/materialized_view_scheduler.py`
- Include comprehensive indexing (25+ indexes per view)
- Add GIN indexes for JSON feature data with proper casting: `USING GIN((column::jsonb))`
- Create refresh functions: `refresh_<view_name>()`
- Update APS scheduler for automated refresh
- Add admin routes for manual refresh and monitoring
- Use proper disease filtering with ILIKE patterns
- Include grade IDs and selected features JSON for each grader

**Database Migration Best Practices:**
- Always include proper downgrade functions
- Drop indexes in reverse creation order
- Include comprehensive comments in SQL
- Use proper naming conventions: `idx_<view>_<column>`
- Add refresh functions in upgrade function

### Authentication & Authorization
**Role-Based Access Control:**
```python
from auth.roles import roles_required
from flask_login import login_required

# Single role requirement
@bp.route("/admin")
@roles_required("admin")
def admin_view():
    # Only admins can access

# Multiple role requirement
@bp.route("/data-manager")
@roles_required("admin", "data_manager")
def data_manager_view():
    # Admins or data managers can access

# Login required for any authenticated user
@bp.route("/profile")
@login_required
def profile_view():
    # Any logged-in user can access
```

**Available Roles:**
- `admin` - Full administrative access
- `data_manager` - Data management and reporting access
- `grader` - Grading and review access
- `viewer` - Read-only access

### Logging Implementation
**Structured Logging Pattern:**
```python
import logging
from flask import current_app

# Get application logger
logger = logging.getLogger(__name__)

# Use context managers for structured logging
def process_grade_data():
    logger.info("Starting grade processing")

    try:
        with transaction_scope() as db:
            # Log with context
            logger.info(f"Processing grade for user {current_user.username}")

            result = db.execute(text("SELECT * FROM grades WHERE id = :id"), {"id": grade_id}).fetchone()

            if result:
                logger.info(f"Found grade: {result['grade_name']}")
            else:
                logger.warning(f"Grade not found with ID: {grade_id}")

    except Exception as e:
        logger.error(f"Failed to process grade: {str(e)}", exc_info=True)
        raise
```

**Log Configuration in app.py:**
```python
# Configure specialized loggers
logging.basicConfig(level=logging.INFO)

# Application logger
app.logger.setLevel(logging.INFO)

# Specialized loggers for different components
materialized_view_logger = logging.getLogger("materialized_view")
grading_logger = logging.getLogger("grading")
scheduler_logger = logging.getLogger("scheduler")
```

### Timezone-Aware Datetime Handling
**Configuration:**
```python
from utils.env_loader import get_env
import pytz

# Load timezone configuration
default_timezone = get_env("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")
tz = pytz.timezone(default_timezone)
```

**Datetime Storage and Display:**
```python
from datetime import datetime, timedelta
import pytz

# Store all datetimes in UTC
def save_timestamp():
    utc_now = datetime.utcnow()
    # Store UTC in database
    return utc_now

# Convert to local timezone for display
def get_local_time(utc_dt):
    if utc_dt is None:
        return None

    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)

    tz = pytz.timezone("Asia/Kolkata")
    return utc_dt.astimezone(tz)
```

**Timezone-Aware Logging:**
```python
import logging
from datetime import datetime
import pytz

def log_with_timezone():
    tz = pytz.timezone("Asia/Kolkata")
    local_time = datetime.now(tz)
    utc_time = datetime.utcnow()

    logger.info(f"IST Time: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"UTC Time: {utc_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
```

**JSON Timestamp Handling:**
```python
def serialize_datetime(dt):
    """Serialize datetime to JSON with timezone info"""
    if dt is None:
        return None

    return {
        'utc': dt.isoformat() if dt.tzinfo else dt.isoformat() + 'Z',
        'local': dt.astimezone(pytz.timezone('Asia/Kolkata')).isoformat()
    }
```

**Timezone Conversion in Queries:**
```python
from utils.datetime_filters import format_user_datetime

# In database operations
def get_recent_grades():
    with transaction_scope() as db:
        result = db.execute(text("""
            SELECT created_at, updated_at
            FROM grades
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)).fetchall()

        for row in result:
            # Convert UTC times to local timezone for display
            local_created = format_user_datetime(row.created_at)
            local_updated = format_user_datetime(row.updated_at)

            logger.info(f"Grade created: {local_created}, Updated: {local_updated}")
```

**Database Migration Best Practices:**
- Always include proper downgrade functions
- Drop indexes in reverse creation order
- Include comprehensive comments in SQL
- Use proper naming conventions: `idx_<view>_<column>`
- Add refresh functions in upgrade function
- Use proper disease filtering with ILIKE patterns
- Include grade IDs and selected features JSON for each grader

### Environment & Deployment
**Docker Development:**
- Always use: `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run <command>`
- Load both environment files for complete configuration
- Use `uv run` instead of direct python commands

### Admin Development
**Materialized View Admin Routes:**
- Create status monitoring endpoints
- Add manual refresh functionality
- Include comprehensive error handling and logging
- Use existing pattern in `admin/materialized_view_status.py`

## Materialized View Ecosystem

### **Advanced Analytics Platform**
The system includes comprehensive materialized views for ophthalmology research and analysis:

#### **Available Views:**
1. **`mvw_grading_data_all`** - General grading data for all diseases
2. **`mvw_diabetic_retinopathy_grading_pivot`** - DR-specific pivoted analysis
3. **`mvw_glaucoma_grading_pivot`** - Glaucoma-specific pivoted analysis
4. **`mvw_amd_grading_pivot`** - AMD-specific pivoted analysis

#### **Key Features:**
- **Pivoted Format:** Each grader type (resident, resident2, arbitrator, review) in separate columns
- **Grade IDs:** Primary keys for direct record access
- **Feature JSON:** Complete feature selections per grader with GIN indexing
- **Performance Optimized:** 25+ indexes per view for fast analytics
- **Automated Refresh:** APS scheduler with 4x daily refresh (07:00, 13:30, 19:00, 01:30 IST)

#### **Admin Interface:**
- **Status Monitoring:** `/admin/materialized-view` - Real-time status and history
- **Manual Refresh:** Manual trigger capabilities with detailed logging
- **Refresh History:** Complete tracking of all refresh operations
- **Performance Metrics:** Per-view timing and success statistics

#### **Usage Examples:**
```sql
-- Query specific disease data
SELECT * FROM mvw_diabetic_retinopathy_grading_pivot WHERE resident_grade = 'Moderate NPDR';

-- Feature analysis with JSON queries
SELECT * FROM mvw_amd_grading_pivot
WHERE resident_features::jsonb @> '[{"label": "Drusen"}]';

-- Grader comparison analysis
SELECT resident_grade, arbitrator_grade, COUNT(*) as count
FROM mvw_glaucoma_grading_pivot
GROUP BY resident_grade, arbitrator_grade;
```

## 1. Project Overview
This project is a comprehensive system for an eye hospital to manage retinal fundus images.
- Ingestion of ZIPs containing images and PDF reports of DR, glaucoma, and AMD screening from Remedio Camera
- Ingestion of images from other cameras
- Scoping source of images, type of camera, Type of image
- Generation of curated datasets for training, dual grading by resident and ophthalmologist with arbitration
- Capturing Artificial Intelligence (AI) models grades for core diseases: Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD)
- Advanced analytics platform with disease-specific materialized views for research and quality assurance 
