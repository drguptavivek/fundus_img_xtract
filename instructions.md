
2. use `uv run` to run commands 
3. DO MOT use python run, python compile, etc. Ass uses Virtual Environment in .venv
4. App uses port `http://127.0.0.1:5001` 
5. Login endpoint is /login
6. All routes are protected  except those listed in app.py:_require_login_everywhere
7. base.html JINJA  template exposes -   {% block extra_styles %},     {% block content %},   {% block page_scripts %}. It also imports     {% from "_forms.html" import csrf_field %}


## Technical Stack
- Docker containers: 
    - web container contains app
    - db container = postgres 18
    - cache container = redis for flask limiter and object cache
- Backend: Flask with SQLAlchemy
- Migrations - alembic to generate migrations and apply migrat
- Frontend: Bootstrap 5.3 with custom SCSS
- Database: PostgreSQL
- Package Manager: uv for Python, npm for CSS
- Testing: pytest

## Docker commands - DEVELOPMENT

```
cp develop.config.env.example develop.config.env
cp docker-compose.override.yml.example docker-compose.override.yml 
docker compose --env-file deploy.config.env --env-file deploy.secrets.env build  web
docker compose --env-file deploy.config.env --env-file deploy.secrets.env up -d db cache
docker compose --env-file deploy.config.env --env-file deploy.secrets.env up web -d
docker compose --env-file deploy.config.env --env-file deploy.secrets.env logs web -f

```


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
- **Database:** SQLAlchemy 
- **Custom JS:** Flash-Toasts.js, photoswipe, edit_image.js, app.js, etc in /static/js
-  **CSS:**  Bootstrap 5.3 via SCSS. Overides in app.css
- **Reusable Partials:** -  _forms.html for CSRF, _viewer_card.html
- **Environment:**  .env and .env.example

##  Common Commands
### Development
- `uv run  app.py` - Run the application 
- `uv pip install` - Install dependencies with uv
- `npn run build:css` - Build Theme 

- Alembic migrations:
  - Check heads before creating: `docker compose --env-file deploy.config.env --env-file deploy.secrets.env exec web uv run alembic heads` (should be a single head).
  - If multiple heads exist, create a merge revision first (e.g., `... exec web uv run alembic merge -m "merge heads" head1 head2`), then generate your migration from the unified head.
  - Generate with Alembic (not manual files): `... exec web uv run alembic revision -m "message" --autogenerate`.
  - Apply with: `... exec web uv run alembic upgrade head`.
- CSRF for JS: include the token from `<meta name="csrf-token">` in AJAX requests via `X-CSRFToken` (see docs/10-DEVELOP/JavaScript_Guidance.md).

- PORT 5001
- use virtual enviroinment .venv


## CODING PROTOCOL ##
**Coding Instructions**
- First understand the request and ask clarifying questions
- Explain your approach step-by-step before writing any code.
- No unrelated edits - focus on just the task you're on
- Follow PEP 8 style guidelines
- Apply PEP 484 type annotations
- Proper memory management
- Always close db sessions
- Choose efficent query loading
- Use proper dependency injection
- Implement proper request validation
- Implement proper error handling and exceptions
- Use explicit error handling, no unwraps in production code
- Build Logic First, then build front-end template. 
- Use Secure Coding practices
- Ensure CSRF protection in all forms  @templates/_forms.html   
- Enusre SQL Injection security
- Add allowed roles for each route
- Use Flash toasts for user feedback
- Use availabe styles only 
- Keep code modular using blueprints
- Include docstrings 
- Organize templates in sub-folders
- Ensure no data is lost.
- No sweeping changes
- Commit small, frequent changes for readable diff.


## 1. Project Overview
This project is a comprehensive system for an eye hospital to manage retinal fundus images. 
- Ingestion of ZIPs containg images and PDF reports of DR and glaucoam screening from Remedio Camera
- Ingestion of images from other cameras
- Scoping source of images, type of camera, Type of image
generation of curated datasets for training, cuual grading by resiednt and ophthalmologist wioth arbiotration
Capturing  Artificial Intelligence (AI) models grades for core diseases Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD). 

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
