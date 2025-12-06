# KiloCode Instructions for Fundus Image Manager

## Overview
This directory contains comprehensive instructions for KiloCode to work effectively with the Fundus Image Manager project.


## When working with code
1. The user uses `uv run app.py`  in VS Code terminal that blcoks the port
2. NEVER do `uv run app.py` as the port is blocked.
    - DO NOT try tu start app yourself. 
    - Always use `uv run` to run commands or scripts, check copile errors etc
    - DO NOT USE `python cmd.py` or `python -c file.py` etc. 
3. DO NOT use python run, python compile, etc. Ass uses Virtual Environment in .venv
4. App uses port `http://127.0.0.1:5001` 
5. Login endpoint is `http://127.0.0.1:5001/login`. Use the script 
6. All routes are protected  except those listed in app.py:_require_login_everywhere
7. base.html JINJA  template exposes -   {% block extra_styles %},     {% block content %},   {% block page_scripts %}. It also imports     {% from "_forms.html" import csrf_field %}
8. Do NOT  Apply `bg-light` class as app uses dark mode and bg-lightg makes text unreadable in dark mode

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

### Database Session Management for KPI API
**Important**: For KPI API implementation, the `@with_session()` decorator should be used as a context manager, not just as a decorator.

**Correct Usage Pattern** (as seen in `api/kpis/encounter_files.py`):
```python
@api_bp.route('/kpis/encounter-files/example', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
def example_endpoint():
    """Example KPI endpoint with proper session management."""
    with with_session() as db:
        try:
            # Database operations here
            query = db.query(SomeModel)
            result = query.all()
            
            return create_kpi_response({"data": result})
            
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            return create_error_response("Internal server error", str(e), 500)
```

**Incorrect Usage Pattern**:
```python
@with_session()  # WRONG: Using as decorator only
def example_endpoint(db):
    # This pattern is not recommended for KPI endpoints
    # as it doesn't provide proper error handling
    query = db.query(SomeModel)
    return query.all()
```

**Key Points for KPI Endpoints**:
1. Always use `with with_session() as db:` pattern for KPI endpoints
2. This ensures proper session management and automatic cleanup
3. Provides better error handling with try/except blocks
4. Follows the pattern established in `api/kpis/encounter_files.py`
5. Ensures database sessions are properly closed even when exceptions occur

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
from dotenv import load_dotenv
import os

load_dotenv()
secret_key = os.getenv("FLASK_SECRET_KEY", "default-value")
is_debug = str(os.getenv("DEBUG", "false")).lower() in ("1", "true", "yes")
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
