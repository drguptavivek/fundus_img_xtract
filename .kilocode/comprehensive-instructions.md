# Fundus Image Manager - Comprehensive KiloCode Instructions

## Project Overview
This is a comprehensive Flask-based system for an eye hospital to manage retinal fundus images, featuring dual grading workflows, AI model integration, and medical data processing.

## Development Environment Setup

### Prerequisites
- Python 3.8+
- Node.js (for CSS building)
- uv (Python package manager)

### Getting Started

1. **Install dependencies with uv:**
```bash
uv pip install
```

2. **Set up environment:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Build CSS assets:**
```bash
npm run build:css:all
```

4. **Run application:**
```bash
uv run app.py
```

The app will be available at `http://127.0.0.1:5001` (or port specified in FLASK_PORT)

## Project Structure & Conventions

### Blueprint Architecture
The application uses Flask blueprints for modular organization:

- **`account/`** - User profile and account management
- **`admin/`** - Administrative functions and user management
- **`analytics/`** - Data analysis and reporting
- **`api/`** - REST API endpoints
- **`auth/`** - Authentication and authorization
- **`direct_uploads/`** - Direct image upload functionality
- **`grading/`** - Dual grading system and arbitration
- **`jobs/`** - Background job processing
- **`media/`** - Media file handling
- **`notifications/`** - User notification system
- **`remedio_zip_uploads/`** - Remedio camera ZIP processing
- **`reports/`** - Report generation
- **`screenings/`** - Screening data management
- **`search/`** - Search functionality
- **`tasks/`** - Grading task management
- **`review/`** - Review and discrepancy handling

### Blueprint Registration Pattern
When adding new blueprints, follow this pattern in `app.py`:

```python
from new_blueprint import bp as new_blueprint_bp
app.register_blueprint(new_blueprint_bp)
```

Each blueprint should have:
- `__init__.py` with blueprint definition
- `routes.py` with route handlers
- Template folder in `templates/blueprint_name/`
- Static assets in `static/blueprint_name/` (if needed)

### Blueprint Structure
```python
# my_module/__init__.py
from flask import Blueprint
bp = Blueprint("my_module", __name__, template_folder="templates")

# Import routes at the end
from . import routes
```

### Database Models
- All models defined in `models.py`
- Use SQLAlchemy with declarative base
- Follow naming conventions:
  - Table names: snake_case plural
  - Column names: snake_case
  - Relationships: descriptive names
- Always include proper foreign key constraints
- Add indexes for performance-critical queries

### Template Organization
- Base template: `templates/base.html`
- Reusable partials: `templates/_partials/`
- Blueprint-specific templates: `templates/blueprint_name/`
- Error pages: `templates/errors/`
- Use Bootstrap 5.3 with custom SCSS overrides

### CSS/SCSS Management
- Source files in `assets/scss/`
- Build with npm scripts:
  - `npm run build:css` - Main theme
  - `npm run build:css:light` - Light theme
  - `npm run build:css:dark` - Dark theme
  - `npm run build:css:all` - All themes
- Output in `static/css/`

## Development Workflow & Best Practices

### Code Style Guidelines
- Follow PEP 8 for Python code
- Use PEP 484 type annotations
- Include docstrings for all functions and classes
- Keep functions focused and small
- Use explicit error handling

### Environment Variables

#### Loading and Using Environment Variables:
```python
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Access environment variables with defaults
secret_key = os.getenv("FLASK_SECRET_KEY", "default-value")
max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
```

#### Environment Variable Categories:
1. **Flask & App Configuration**: FLASK_SECRET_KEY, ASSETS_VERSION, STATIC_MAX_AGE, WORKERS
2. **Database**: DATABASE_URL
3. **Directories**: UPLOAD_DIR, IMAGE_DIR, PDF_DIR, etc.
4. **Upload Limits**: MAX_CONTENT_LENGTH, PER_FILE_MAX_BYTES, MAX_FILES_PER_UPLOAD
5. **Logging**: HTTP_SUCCESS_LOG, HTTP_ERROR_LOG, ZIP_INGEST_LOG, etc.
6. **Email**: SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL
7. **Session & Security**: SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE, INACTIVITY_TIMEOUT_MINUTES

#### Best Practices:
- Always provide sensible defaults when accessing environment variables
- Use .env.example as a template for required environment variables
- Convert string values to appropriate types (int, bool) when needed
- Group related configuration in app.config

#### Configuration in Flask App:
```python
# In create_app() function
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
app.config["PER_FILE_MAX_BYTES"] = int(os.getenv("PER_FILE_MAX_BYTES", 10 * 1024 * 1024))
app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER")
app.config["SESSION_COOKIE_SECURE"] = str(os.getenv("SESSION_COOKIE_SECURE", "false")).lower() == "true"

# Boolean conversion pattern
is_debug = str(os.getenv("DEBUG", "false")).lower() in ("1", "true", "yes")
```

### Directory Structure

#### Use Environment Variables for Directory Paths:
```python
# Define directories in .env
UPLOAD_DIR=files/zip_upload_zips
IMAGE_DIR=files/zip_upload_images
PDF_DIR=files/zip_upload_pdfs

# Access in code
upload_dir = os.getenv("UPLOAD_DIR", "files/uploads")
image_dir = os.getenv("IMAGE_DIR", "files/images")
```

#### Directory Creation Pattern:
```python
from pathlib import Path

# Ensure directories exist
def ensure_directory(path):
    Path(path).mkdir(parents=True, exist_ok=True)

# Usage
ensure_directory(os.getenv("UPLOAD_DIR", "files/uploads"))
```

### Database Session Management

#### Preferred Method - Using Context Manager:
```python
from utils.utils import with_session

@with_session()
def my_function(db):
    # Use db session here
    user = db.get(User, user_id)
    # No need to commit/close - handled automatically
```

#### Manual Session Management:
```python
from models import Session
db = Session()
try:
    # Database operations
    db.commit()
except Exception as e:
    db.rollback()
    raise e
finally:
    db.close()
```

### Form Handling
- Use Flask-WTF for all forms
- Include CSRF protection using proper import pattern
- Validate input data properly
- Use flash messages for user feedback

#### CSRF Protection Pattern:
```html
{% from 'templates/_forms.html' import csrf_field %}
<form method="POST">
    {{ csrf_field() }}
    <!-- form fields -->
</form>
```

### Authentication & Authorization
- Use Flask-Login for user sessions
- Role-based access control via `@roles_required('role_name')`
- Check permissions in routes using `current_user.has_role()`
- Lab unit-based data scoping

#### Route Protection Pattern:
```python
from auth.roles import roles_required

@bp.route("/admin")
@roles_required("admin", "data_manager")
def admin_view():
    # Only admins and data managers can access
```

#### Resource Ownership Checks:
```python
from utils.utils import require_owner_or_roles

# Check if user has admin/data_manager role OR is the owner
if not require_owner_or_roles(upload, 'admin', 'data_manager'):
    flash("Permission denied", "danger")
    return redirect(url_for("dashboard"))
```

Note: `require_owner_or_roles` checks if the current user either:
1. Has any of the specified roles, OR
2. Is the owner of the resource (upload.uploader_id == current_user.id)

### Logging Configuration

#### Use dedicated loggers:
```python
import logging

auth_logger = logging.getLogger("auth")
editing_logger = logging.getLogger("editing")
grades_logger = logging.getLogger("grades")
```

#### Log with context:
```python
auth_logger.info("User login - User: %s, IP: %s", username, ip)
editing_logger.info("Edited upload_id=%s user_id=%s", upload.id, current_user.id)
```

#### Environment Variables for Log Paths:
```python
# Define log paths in .env
HTTP_SUCCESS_LOG=logs/http_success.log
HTTP_ERROR_LOG=logs/http_error.log
ZIP_INGEST_LOG=logs/zip_main_process_log.txt
```

### Blueprint Registration

#### Register in app.py after logging setup:
```python
from my_module import bp as my_module_bp
app.register_blueprint(my_module_bp)
```

### Error Handling

#### Use flash-toasts for user feedback:
```python
from flask import flash

flash("Operation successful", "success")
flash("Error occurred", "danger")
```

#### Log exceptions with context:
```python
try:
    risky_operation()
except Exception as e:
    logger.exception("Failed operation: %s", operation_id)
    flash("Operation failed", "danger")
```

### Form Validation

#### Use Flask-WTF forms:
```python
from flask_wtf import FlaskForm
from wtforms import StringField, validators

class MyForm(FlaskForm):
    name = StringField('Name', [validators.Length(min=3, max=50)])
```

### API Endpoints

#### Use api blueprint:
```python
# api/my_endpoints.py
from . import api_bp

@api_bp.route('/resource', methods=['GET'])
@login_required
@roles_required("admin")
def get_resource():
    return jsonify(data)
```

### Database Models

#### Use UTC timestamps:
```python
from datetime import datetime, timezone

created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), 
    default=datetime.now(timezone.utc)
)
```

#### Include proper relationships:
```python
from sqlalchemy.orm import relationship

user: Mapped["User"] = relationship(back_populates="uploads")
```

### Testing

#### Use test pattern:
```python
def test_feature():
    with app.test_client() as client:
        # Setup test data
        # Make request
        response = client.get('/route')
        # Assert response
        assert response.status_code == 200
```

## Security Considerations

### CSRF Protection
- All forms must include CSRF token
- Use `templates/_forms.html` partial
- Verify CSRF in AJAX requests

### SQL Injection Prevention
- Use SQLAlchemy ORM queries
- Never concatenate raw SQL
- Validate all user inputs
- Use parameterized queries

### File Upload Security
- Validate file types and sizes
- Scan for malicious content
- Store uploads outside web root
- Use secure file naming

### Session Security
- Use secure cookie settings
- Implement proper logout
- Session timeout handling
- Rate limiting on auth endpoints

## Performance Optimization

### Database Queries
- Use efficient query patterns
- Add appropriate indexes
- Avoid N+1 query problems
- Use query optimization

### Caching
- Static asset caching
- Database query caching
- Session caching
- Rate limiting

### Background Jobs
- Use job queue for long tasks
- Monitor job processing
- Handle job failures
- Log job activities

## Deployment

### Environment Configuration

#### Loading Environment Variables:
```python
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Access environment variables with defaults
secret_key = os.getenv("FLASK_SECRET_KEY", "default-value")
max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))

# Boolean conversion pattern
is_debug = str(os.getenv("DEBUG", "false")).lower() in ("1", "true", "yes")
```

#### Configuration in Flask App:
```python
# In create_app() function
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
app.config["SESSION_COOKIE_SECURE"] = str(os.getenv("SESSION_COOKIE_SECURE", "false")).lower() == "true"
```

### Production Setup
- Use WSGI server (Gunicorn/uWSGI)
- Configure reverse proxy
- Set up SSL certificates
- Monitor application health

#### Directory Management:
```python
from pathlib import Path

# Ensure directories exist
def ensure_directory(path):
    Path(path).mkdir(parents=True, exist_ok=True)

# Usage
ensure_directory(os.getenv("UPLOAD_DIR", "files/uploads"))
```

## Troubleshooting

### Common Issues
1. **Port conflicts:** Check FLASK_PORT in .env
2. **Database errors:** Verify DATABASE_URL
3. **CSS not updating:** Run `npm run build:css`
4. **Permission errors:** Check file permissions
5. **Import errors:** Verify Python path

### Debug Mode
- Enable debug logging in .env
- Check logs in `logs/` directory
- Use Flask debugger in development
- Monitor database queries

## Key Files to Understand

- **`app.py`** - Main application factory and configuration
- **`models.py`** - Database models and relationships
- **`.env.example`** - Environment configuration template
- **`AGENTS.md`** - Development guidelines and protocols
- **`requirements.txt.lock`** - Python dependencies
- **`package.json`** - Node.js dependencies and scripts

## Medical Data Handling

### HIPAA Compliance
- Encrypt sensitive data
- Audit data access
- Secure data transmission
- Proper data retention

### Patient Data Privacy
- Anonymize patient identifiers
- Control data access
- Log data access attempts
- Secure data disposal

## AI Model Integration

### Model Management
- Register AI models in admin panel
- Version control for models
- Model performance monitoring
- A/B testing capabilities

### Grading Workflow
- Dual grading system
- Arbitration for discrepancies
- Consensus building
- Quality assurance

## Mode-Specific Instructions

### Architect Mode

#### When to Use
- Planning new features or major refactoring
- Designing system architecture
- Creating technical specifications
- Planning database schema changes
- Designing API endpoints

#### Key Considerations
1. **Medical Data Sensitivity**: Always consider HIPAA compliance and data privacy
2. **Dual Grading Workflow**: Understand the resident → resident2 → arbitration flow
3. **Role-Based Access**: Plan permissions carefully for different user roles
4. **Audit Requirements**: Medical systems need comprehensive audit trails

#### Planning Checklist
- [ ] Identify all user roles affected
- [ ] Consider data privacy implications
- [ ] Plan database migrations carefully
- [ ] Design proper error handling
- [ ] Include logging and audit trails
- [ ] Consider performance impact
- [ ] Plan testing strategy

### Code Mode

#### When to Use
- Implementing new features
- Fixing bugs
- Refactoring existing code
- Adding new routes or endpoints
- Database modifications

#### Code Standards
1. **Follow PEP 8** strictly
2. **Use type annotations** (PEP 484)
3. **Include docstrings** for all functions
4. **Handle errors explicitly**
5. **Close database sessions** properly

#### Database Operations
```python
# Always use this pattern
from utils.utils import with_session

@with_session()
def my_function(db):
    # Use db session here
    user = db.get(User, user_id)
    # No need to commit/close - handled automatically
```

#### Form Handling
- Always use Flask-WTF
- Include CSRF protection
- Validate input data
- Use flash messages for feedback

#### Route Development
```python
# Standard route pattern
@bp.route("/endpoint")
@login_required
@roles_required("admin", "data_manager")
def endpoint():
    # Your code here
    return render_template("template.html")
```

#### Security Requirements
- Validate all inputs
- Use parameterized queries
- Implement proper authentication
- Check user permissions
- Log security events

### Ask Mode

#### When to Use
- Explaining existing code
- Providing technical documentation
- Answering questions about architecture
- Explaining medical workflows
- Clarifying business logic

#### Key Areas to Explain
1. **Dual Grading System**: How resident grading and arbitration works
2. **Image Processing Pipeline**: From upload to grading
3. **Role-Based Access**: Different permissions and capabilities
4. **Medical Data Flow**: How patient data moves through the system
5. **AI Integration**: How AI models are integrated with manual grading

### Debug Mode

#### When to Use
- Investigating bugs or errors
- Performance issues
- Unexpected behavior
- Data inconsistencies
- Integration problems

#### Debugging Strategy
1. **Check Logs First**: Look in `logs/` directory
2. **Reproduce Issue**: Create consistent reproduction steps
3. **Isolate Problem**: Narrow down the affected component
4. **Check Database**: Verify data integrity
5. **Review Recent Changes**: Look for recent modifications

#### Common Debugging Areas
- **Authentication Issues**: Check session handling and roles
- **Database Problems**: Verify queries and connections
- **File Upload Errors**: Check permissions and validation
- **Grading Workflow**: Verify task assignments and states
- **Performance Issues**: Check query efficiency and caching

#### Debugging Tools
- Application logs in `logs/` directory
- Flask debugger in development
- Database query logging
- Browser developer tools
- Python debugger (pdb)

### Orchestrator Mode

#### When to Use
- Complex, multi-step projects
- Coordinating work across different domains
- Managing large-scale refactoring
- Implementing major new features
- System integration projects

#### Project Coordination
1. **Break Down Tasks**: Create manageable subtasks
2. **Identify Dependencies**: Understand task relationships
3. **Assign Appropriate Modes**: Use the right mode for each subtask
4. **Monitor Progress**: Track completion and quality
5. **Handle Integration**: Ensure components work together

## Quick Reference

### Essential Commands

#### Development
```bash
# Install dependencies
uv pip install

# Run application
uv run app.py

# Build CSS
npm run build:css:all

# Watch CSS during development
npm run watch:css
```

#### Environment Setup
```bash
# Copy environment template
cp .env.example .env

# Key environment variables
FLASK_PORT=5001
DATABASE_URL=sqlite:///image_manager.db
FLASK_SECRET_KEY=your-secret-key
```

### Project Structure

#### Core Files
- **`app.py`** - Main application factory
- **`models.py`** - All database models
- **`.env.example`** - Environment configuration
- **`AGENTS.md`** - Development guidelines

#### Key Directories
- **`templates/`** - Jinja2 templates
- **`static/`** - Static assets (CSS, JS, images)
- **`logs/`** - Application logs
- **`files/`** - File storage (uploads, processing)

### Database Patterns

#### Session Management

##### Preferred Method - Context Manager:
```python
from utils.utils import with_session

@with_session()
def my_function(db):
    # Use db session here
    user = db.get(User, user_id)
    # No need to commit/close - handled automatically
```

##### Manual Method:
```python
from models import Session
db = Session()
try:
    # Database operations
    db.commit()
except Exception as e:
    db.rollback()
    raise e
finally:
    db.close()
```

### Route Patterns

#### Standard Route
```python
from auth.roles import roles_required

@bp.route("/endpoint")
@login_required
@roles_required("admin", "data_manager")
def endpoint():
    return render_template("template.html")
```

#### Resource Ownership Check
```python
from utils.utils import require_owner_or_roles

# Check if user has admin/data_manager role OR is the owner
if not require_owner_or_roles(upload, 'admin', 'data_manager'):
    flash("Permission denied", "danger")
    return redirect(url_for("dashboard"))
```

### Form Handling

#### CSRF Protection
```html
<!-- Include in all forms -->
{% from 'templates/_forms.html' import csrf_field %}
<form method="POST">
    {{ csrf_field() }}
    <!-- form fields -->
</form>
```

### Security Requirements

#### Authentication
- Use `@login_required` for protected routes
- Check roles with `@roles_required('role_name')`
- Verify permissions with `current_user.has_role()`

#### Input Validation
- Validate all user inputs
- Use SQLAlchemy ORM to prevent SQL injection
- Sanitize file uploads
- Implement rate limiting

### Common Workflows

#### Adding New Blueprint
1. Create directory: `blueprint_name/`
2. Add `__init__.py` with blueprint definition:
   ```python
   from flask import Blueprint
   bp = Blueprint("my_module", __name__, template_folder="templates")
   from . import routes
   ```
3. Add `routes.py` with route handlers
4. Create templates in `templates/blueprint_name/`
5. Register in `app.py` after logging setup:
   ```python
   from my_module import bp as my_module_bp
   app.register_blueprint(my_module_bp)
   ```

#### Adding Database Model
1. Define class in `models.py`
2. Add proper relationships and constraints
3. Create migration if needed
4. Update related forms and templates

#### Adding New Route
1. Add route to appropriate blueprint
2. Include authentication and role checks
3. Create template
4. Add navigation links
5. Test with different user roles

### Error Handling

#### Logging
```python
import logging

# Use dedicated loggers
auth_logger = logging.getLogger("auth")
editing_logger = logging.getLogger("editing")
grades_logger = logging.getLogger("grades")

# Log with context
auth_logger.info("User login - User: %s, IP: %s", username, ip)
```

### Testing

#### Running Tests
```bash
# Unit tests
pytest tests/

# E2E tests
npx playwright test
```

#### Test Structure
- Unit tests in `tests/`
- E2E tests in `e2e/`
- Test with different user roles
- Test file upload functionality

### Medical Data Considerations

#### HIPAA Compliance
- Never log patient data
- Use secure connections
- Implement proper access controls
- Audit data access

#### Data Privacy
- Anonymize patient identifiers
- Control data access by role
- Secure data transmission
- Proper data retention

### Common Issues

#### Port Conflicts
- Check `FLASK_PORT` in `.env`
- Default is 5001
- Ensure port is not in use

#### Database Issues
- Verify `DATABASE_URL` in `.env`
- Check file permissions
- Run database migrations

#### JS/CSS Not Updating
- Check static file caching
- Verify asset version in `.env`

### Key User Roles

#### Medical Roles
- **admin** - System administration
- **data_manager** - Data management
- **ophthalmologist** - Medical expert
- **resident** - Grading resident
- **arbitrator** - Dispute resolution

#### Permissions
- Use `@roles_required()` decorator
- Check permissions in routes
- Implement lab unit-based access
- Audit permission changes

### Development Tips

#### Code Style
- Follow PEP 8
- Use type annotations
- Include docstrings
- Keep functions small

#### Performance
- Use database indexes
- Implement caching
- Optimize queries
- Monitor slow operations

#### Security
- Validate all inputs
- Use HTTPS in production
- Implement rate limiting
- Regular security audits

## Email Functions

#### Quick Reference:
```python
from utils.emails import send_email, send_email_sync, send_otp_email

# Asynchronous email sending (preferred)
email_thread = send_email(
    to_email="user@example.com",
    subject="Subject",
    body="Email body",
    callback=lambda success: print(f"Email sent: {success}")
)

# Send OTP asynchronously
otp_thread = send_otp_email(
    to_email="user@example.com",
    username="username",
    otp="12345678",
    callback=lambda success: print(f"OTP sent: {success}")
)
```

#### Email Configuration (.env):
```bash
SMTP_SERVER=localhost
SMTP_PORT=587
SMTP_USERNAME=xxxx
SMTP_PASSWORD=yyyyy
FROM_EMAIL=noreply@example.com
EMAIL_DEBUG_LOGGING=false
```

## Datetime Handling

#### Quick Reference:
```python
from datetime import datetime, timezone
from utils.timezone_choices import DEFAULT_TIMEZONE

# Current time in UTC
now = datetime.now(timezone.utc)

# Store in UTC, display in user timezone
created_at = datetime.now(timezone.utc)
# Display (in template): {{ user_datetime(obj.created_at) }}
```

This comprehensive guide provides KiloCode with all the essential information needed to work effectively with the Fundus Image Manager project, following all established conventions and medical domain requirements.