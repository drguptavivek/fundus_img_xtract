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
