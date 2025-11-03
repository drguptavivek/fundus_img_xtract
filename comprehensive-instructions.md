# Comprehensive Instructions for Fundus Image Manager

## Project Overview

This is a comprehensive system for an eye hospital to manage retinal fundus images. It facilitates the generation of curated datasets for training and validating Artificial Intelligence (AI) models targeted at detecting Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD).

## Development Environment Setup

### 1. Initial Setup

```bash
# Clone the repository
git clone https://github.com/drguptavivek/fundus_img_xtract.git
cd fundus_img_xtract

# Set up Python environment with uv
uv init
uv add -r requirements.txt

# OR with traditional Python
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Database Setup

```bash
# Set up database using Alembic migrations
uv run alembic upgrade head

# Create initial user and assign roles
python -m scripts.create_user
python -m scripts.assign_roles admin --roles admin
```

### 3. Running the Application

```bash
# Development server
uv run app.py

# The application runs on http://127.0.0.1:5001
```

## Key Technical Components

### Database Management with Alembic

The project uses **Alembic** for database schema management:

- **Configuration**: [`alembic.ini`](alembic.ini)
- **Environment Setup**: [`migrations/env.py`](migrations/env.py)
- **Migration Files**: [`migrations/versions/`](migrations/versions/)

#### Common Alembic Commands

```bash
# Create new migration
uv run alembic revision --autogenerate -m "Description of changes"

# Apply migrations
uv run alembic upgrade head

# Check current status
uv run alembic current

# View migration history
uv run alembic history

# Rollback migration
uv run alembic downgrade <revision_id>
```

**Detailed Documentation**: [Alembic Database Migrations](docs/alembic-migrations.md)

### Application Architecture

- **Backend**: Flask with SQLAlchemy ORM
- **Database**: SQLite (development) / PostgreSQL (production)
- **Frontend**: Bootstrap 5.3 with custom SCSS
- **Package Management**: uv for Python, npm for CSS
- **Testing**: pytest + Playwright

### Key Directories

- [`models.py`](models.py) - SQLAlchemy database models
- [`app.py`](app.py) - Main Flask application
- [`utils/`](utils/) - Utility functions and helpers
- [`scripts/`](scripts/) - Database and maintenance scripts
- [`templates/`](templates/) - Jinja2 HTML templates
- [`static/`](static/) - Static assets (CSS, JS, images)

## Development Workflow

### 1. Making Database Changes

```bash
# 1. Update models.py
# 2. Generate migration
uv run alembic revision --autogenerate -m "Add new field to table"

# 3. Review migration file
# 4. Apply migration
uv run alembic upgrade head
```

### 2. Adding New Features

1. Follow the existing code structure and patterns
2. Use blueprints for modular organization
3. Implement proper authentication and authorization
4. Add appropriate logging
5. Write tests for new functionality

### 3. Database Session Management

Use the context manager from `utils.utils`:

```python
from utils.utils import with_session

@with_session()
def my_function(db):
    # Use db session here
    user = db.get(User, user_id)
    # No need to commit/close - handled automatically
```

### 4. Authentication & Authorization

```python
from auth.roles import roles_required

@bp.route("/admin")
@roles_required("admin", "data_manager")
def admin_view():
    # Only admins and data managers can access
```

### 5. CSRF Protection

All forms must include CSRF token:

```html
<form method="POST">
    {{ csrf_field() }}
    <!-- form fields -->
</form>
```

## Coding Standards

### Python Code

- Follow PEP 8 style guidelines
- Apply PEP 484 type annotations
- Use proper error handling
- Include docstrings for functions and classes
- Use explicit error handling, no unwraps in production code

### Database Operations

- Choose efficient query loading
- Use proper dependency injection
- Implement proper request validation
- Always close db sessions (use context managers)

### Security Practices

- Ensure CSRF protection in all forms
- Prevent SQL injection
- Validate all inputs
- Use secure coding practices

### Frontend Code

- Use available styles only
- Follow Bootstrap conventions
- Implement responsive design
- Use JavaScript for dynamic interactions

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_auth.py

# Run with coverage
pytest --cov=.
```

### End-to-End Testing

The project uses Playwright for E2E tests:

```bash
# Install Playwright browsers
npx playwright install

# Run E2E tests
npx playwright test
```

## Deployment

### Environment Variables

Key environment variables (see [`.env.example`](.env.example)):

```bash
FLASK_SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///image_manager.db  # or PostgreSQL URL
DEBUG=false
```

### Production Setup

1. Set up PostgreSQL database
2. Configure environment variables
3. Run migrations: `uv run alembic upgrade head`
4. Set up reverse proxy (nginx)
5. Configure WSGI server (gunicorn)

## Documentation

### Key Documentation Files

- [Project README](README.md) - Project overview and setup
- [Alembic Migrations](docs/alembic-migrations.md) - Database migration guide
- [Development Conventions](docs/10-DEVELOP/CONVENTIONS.md) - Coding standards
- [Database Models](docs/00-Core/models.md) - Database schema documentation
- [Security Guide](docs/10-DEVELOP/Security.md) - Security best practices
- [API Documentation](docs/routes.md) - API endpoints documentation

### User Guides

Located in [`docs/user-guide/`](docs/user-guide/):

- [Getting Started](docs/user-guide/getting-started.md)
- [Image Upload](docs/user-guide/uploading-images.md)
- [Grading Images](docs/user-guide/grading-images.md)
- [Analytics](docs/user-guide/viewing-analytics.md)

## Troubleshooting

### Common Issues

1. **Database Migration Errors**
   - Check current revision: `uv run alembic current`
   - Verify migration history: `uv run alembic history`
   - Use `alembic stamp` if database state is inconsistent

2. **Import Errors**
   - Ensure virtual environment is activated
   - Install dependencies: `uv pip install -r requirements.txt`

3. **Permission Errors**
   - Check user roles in database
   - Verify role assignments: `python -m scripts.assign_roles`

### Getting Help

1. Check relevant documentation files
2. Review error logs in `logs/` directory
3. Search existing issues in the repository
4. Follow the debugging guidelines in [Development Conventions](docs/10-DEVELOP/CONVENTIONS.md)

## Contributing

### Git Workflow

```bash
# Create feature branch
git checkout -b feature-name

# Make changes and commit
git add .
git commit -m "Description of changes"

# Push and create pull request
git push origin feature-name
```

### Code Review Process

1. Ensure all tests pass
2. Follow coding standards
3. Update documentation as needed
4. Request code review
5. Address feedback before merging

## Quick Reference

### Essential Commands

```bash
# Development
uv run app.py                    # Start development server
uv run alembic upgrade head      # Apply database migrations
uv run alembic revision --autogenerate -m "message"  # Create migration

# Testing
pytest                           # Run tests
npx playwright test               # Run E2E tests

# Database
python -m scripts.create_user     # Create new user
python -m scripts.backup_db       # Backup database
python -m scripts.restore_db      # Restore database
```

### Important Files

- [`app.py`](app.py) - Main application
- [`models.py`](models.py) - Database models
- [`alembic.ini`](alembic.ini) - Alembic configuration
- [`.env.example`](.env.example) - Environment variables template
- [`requirements.txt`](requirements.txt) - Python dependencies

### Port Information

- Application: `http://127.0.0.1:5001`
- Login endpoint: `/login`

## Mode-Specific Instructions

This document provides general instructions. For mode-specific guidance:

- **Code Mode**: Focus on implementation details and coding patterns
- **Architect Mode**: Focus on system design and planning
- **Ask Mode**: Focus on explanations and documentation
- **Debug Mode**: Focus on troubleshooting and issue resolution

---

**Note**: This document is a living resource. Please update it as the project evolves and new patterns emerge.