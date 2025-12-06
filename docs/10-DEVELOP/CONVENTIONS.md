# Development Conventions

This document provides comprehensive guidelines for development practices in the Fundus Image Manager application. It covers essential patterns for database operations, security, logging, and other core aspects of the application.

## Environment Variables

### Loading and Using Environment Variables:
```python
from utils.env_loader import load_environment, get_env
import os

# Load environment variables from .env file
load_environment()

# Access environment variables with defaults
secret_key = get_env("FLASK_SECRET_KEY", "default-value")
max_content_length = int(get_env("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
```

### Environment Variable Categories:
1. **Flask & App Configuration**: FLASK_SECRET_KEY, ASSETS_VERSION, STATIC_MAX_AGE, WORKERS
2. **Database**: DATABASE_URL
3. **Directories**: UPLOAD_DIR, IMAGE_DIR, PDF_DIR, etc.
4. **Upload Limits**: MAX_CONTENT_LENGTH, PER_FILE_MAX_BYTES, MAX_FILES_PER_UPLOAD
5. **Logging**: HTTP_SUCCESS_LOG, HTTP_ERROR_LOG, ZIP_INGEST_LOG, etc.
6. **Email**: SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL
7. **Session & Security**: SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE, INACTIVITY_TIMEOUT_MINUTES

### Best Practices:
- Always provide sensible defaults when accessing environment variables
- Use .env.example as a template for required environment variables
- Convert string values to appropriate types (int, bool) when needed
- Group related configuration in app.config

### Configuration in Flask App:
```python
# In create_app() function
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
app.config["PER_FILE_MAX_BYTES"] = int(os.getenv("PER_FILE_MAX_BYTES", 10 * 1024 * 1024))
app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER")
app.config["SESSION_COOKIE_SECURE"] = str(os.getenv("SESSION_COOKIE_SECURE", "false")).lower() == "true"

# Boolean conversion pattern
is_debug = str(os.getenv("DEBUG", "false")).lower() in ("1", "true", "yes")
```

## Directory Structure

### Use Environment Variables for Directory Paths:
```python
# Define directories in .env
UPLOAD_DIR=files/zip_upload_zips
IMAGE_DIR=files/zip_upload_images
PDF_DIR=files/zip_upload_pdfs

# Access in code
upload_dir = os.getenv("UPLOAD_DIR", "files/uploads")
image_dir = os.getenv("IMAGE_DIR", "files/images")
```

### Directory Creation Pattern:
```python
from pathlib import Path

# Ensure directories exist
def ensure_directory(path):
    Path(path).mkdir(parents=True, exist_ok=True)

# Usage
ensure_directory(os.getenv("UPLOAD_DIR", "files/uploads"))
```

## Logging Configuration

For detailed logging conventions and patterns, see:
- [Logging.md](Logging.md) - Implementation patterns and conventions
- [logging.md](logging.md) - Complete logging infrastructure with dedicated loggers

### Environment Variables for Log Paths:
```python
# Define log paths in .env
HTTP_SUCCESS_LOG=logs/http_success.log
HTTP_ERROR_LOG=logs/http_error.log
ZIP_INGEST_LOG=logs/zip_main_process_log.txt
```

## Database Connections

For detailed database session management patterns, see:
- [DB CONTEXT MANAGER.md](DB CONTEXT MANAGER.md) - Implementation patterns
- [../00-Core/models.md](../00-Core/models.md) - Database models documentation
- [docs/ERD.md](../00-Core/ERD.md) - Entity Relationship Diagram

### Quick Reference:
```python
from utils.utils import with_session

@with_session()
def my_function(db):
    # Use db session here
    user = db.get(User, user_id)
    # No need to commit/close - handled automatically
```

## CSRF Protection

For detailed security information, see [docs/Security.md](Security.md) - Comprehensive authentication, authorization, and security features

### Include CSRF token in all forms:
```html
{% from 'templates/_forms.html' import csrf_field %}
<form method="POST">
    {{ csrf_field() }}
    <!-- form fields -->
</form>
```

### CSRF is automatically enforced on all state-changing requests.

## Datetime Handling

For detailed datetime handling conventions, see [CONVENTIONS/DateTime.md](CONVENTIONS/DateTime.md)

### Quick Reference:
```python
from datetime import datetime, timezone
from utils.timezone_choices import DEFAULT_TIMEZONE

# Current time in UTC
now = datetime.now(timezone.utc)

# Store in UTC, display in user timezone
created_at = datetime.now(timezone.utc)
# Display (in template): {{ user_datetime(obj.created_at) }}
```

## Logging

For detailed logging conventions and patterns, see:
- [Logging.md](Logging.md) - Implementation patterns and conventions
- [logging.md](logging.md) - Complete logging infrastructure with dedicated loggers

### Use dedicated loggers:
```python
import logging

auth_logger = logging.getLogger("auth")
editing_logger = logging.getLogger("editing")
grades_logger = logging.getLogger("grades")
```

### Log with context:
```python
auth_logger.info("User login - User: %s, IP: %s", username, ip)
editing_logger.info("Edited upload_id=%s user_id=%s", upload.id, current_user.id)
```

## Blueprint Registration

### Register in app.py after logging setup:
```python
from my_module import bp as my_module_bp
app.register_blueprint(my_module_bp)
```

### Blueprint structure:
```python
# my_module/__init__.py
from flask import Blueprint
bp = Blueprint("my_module", __name__, template_folder="templates")

# Import routes at the end
from . import routes
```

## Route Protection

### Use role decorators:
```python
from auth.roles import roles_required

@bp.route("/admin")
@roles_required("admin", "data_manager")
def admin_view():
    # Only admins and data managers can access
```

### Resource ownership checks:
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

## Security

For comprehensive security information including authentication, authorization, and security features, see:
- [docs/Security.md](docs/Security.md) - Comprehensive authentication, authorization, and security features
- [docs/routes.md](docs/routes.md) - Route protection and role-based access control

### Key Security Practices:
- Always use CSRF tokens in forms (see CSRF Protection section)
- Implement proper role-based access control
- Validate and sanitize all user inputs
- Use parameterized queries to prevent SQL injection
- Secure session management with proper timeout

## Email Functions

For detailed email system documentation, see [docs/Email.md](Email.md) - Comprehensive email functionality documentation

### Quick Reference:
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

### Email Configuration (.env):
```bash
SMTP_SERVER=localhost
SMTP_PORT=587
SMTP_USERNAME=xxxx
SMTP_PASSWORD=yyyyy
FROM_EMAIL=noreply@example.com
EMAIL_DEBUG_LOGGING=false
```

## Error Handling

### Use flash-toasts for user feedback:
```python
from flask import flash

flash("Operation successful", "success")
flash("Error occurred", "danger")
```

### Log exceptions with context:
```python
try:
    risky_operation()
except Exception as e:
    logger.exception("Failed operation: %s", operation_id)
    flash("Operation failed", "danger")
```

## Form Validation

### Use Flask-WTF forms:
```python
from flask_wtf import FlaskForm
from wtforms import StringField, validators

class MyForm(FlaskForm):
    name = StringField('Name', [validators.Length(min=3, max=50)])
```

## API Endpoints

For detailed API documentation, see:
- [../Utilities/api.md](../Utilities/api.md) - RESTful API endpoints and documentation
- [docs/routes.md](docs/routes.md) - Comprehensive documentation for all application routes

### Use the api blueprint:
```python
# api/my_endpoints.py
from . import api_bp

@api_bp.route('/resource', methods=['GET'])
@login_required
@roles_required("admin")
def get_resource():
    return jsonify(data)
```

## Database Models

### Use UTC timestamps:
```python
from datetime import datetime, timezone

created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), 
    default=datetime.now(timezone.utc)
)
```

### Include proper relationships:
```python
from sqlalchemy.orm import relationship

user: Mapped["User"] = relationship(back_populates="uploads")
```

## Testing

### Use the test pattern:
```python
def test_feature():
    with app.test_client() as client:
        # Setup test data
        # Make request
        response = client.get('/route')
        # Assert response
        assert response.status_code == 200