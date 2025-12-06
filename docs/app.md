# `app.py` Documentation

This document provides a comprehensive overview of the `app.py` file, which serves as the main entry point and configuration hub for the Flask web application.

## Core Function: `create_app()`

The primary component of `app.py` is the `create_app()` function, which follows the **Application Factory** pattern. This pattern is a standard practice in Flask that enhances modularity and testability. Instead of creating a global Flask app instance, the app is created and configured within this function.

### Key Responsibilities of `create_app()`:

1.  **Application Initialization and Configuration:**
    *   **Environment Loading:** Loads application settings from a `.env` file using `python-dotenv`. This keeps sensitive data and environment-specific variables out of the source code.
    *   **Flask App Instantiation:** Creates the core `Flask` object, explicitly setting the `static_folder` for clarity.
    *   **Configuration Loading:** Sets up various application configurations by reading from environment variables with sensible defaults. This includes:
        *   `SECRET_KEY`: For signing session cookies and other security-related needs.
        *   File Upload Limits: `MAX_CONTENT_LENGTH`, `PER_FILE_MAX_BYTES`, `MAX_FILES_PER_UPLOAD`.
        *   Pagination: `UPLOADED_RESULTS_PAGE_SIZE`, `SCREENINGS_PAGE_SIZE`.
        *   Performance: `WORKERS` for the thread pool.
        *   Session Management: Configures session cookie security (e.g., `HTTPOnly`, `Samesite`, `Secure`) and an automatic inactivity timeout with a sliding window.
        *   `ThreadPoolExecutor`: A pool of threads is initialized and attached to the app config, allowing background tasks to be executed without blocking web requests.

2.  **CSRF Protection:**
    *   Initializes `Flask-WTF`'s `CSRFProtect` extension to guard against Cross-Site Request Forgery attacks on all state-changing requests. The CSRF token is set to expire after one hour.
    *   Custom error handler for CSRF failures that redirects users with a helpful flash message.

3.  **CORS Configuration:**
    *   Initializes Flask-CORS for API endpoints, allowing credentials from same-origin requests to handle session cookies properly.
    *   Configured to allow requests from localhost for development purposes.

4.  **Environment and Database Setup:**
    *   Calls `setup_environment()` to ensure that all necessary directories (e.g., for uploads, logs) exist.
    *   **Database Management**: Database tables are now managed by Alembic migrations instead of automatic creation. The app uses SQLAlchemy 2.0+ with PostgreSQL for production.
    *   **Role-Based Access Control (RBAC):** Seeds the database with a predefined set of user roles by calling `auth.roles.ensure_roles()`. This is also an idempotent operation.
    *   **Session Management**: Uses database-backed sessions with `DatabaseSessionInterface` for secure session storage.

5.  **Logging:**
    *   Configures robust, rotating file-based logging for various application components.
    *   Multiple specialized log files are created in the `logs/` directory:
        *   `http_error.log`: Records HTTP errors (status codes `>= 400`)
        *   `runtime_error.log`: Records detailed runtime errors with stack traces
        *   `grades.log`: Records grading-related activities
        *   `auth.log`: Records authentication events
        *   `editing.log`: Records image editing activities
        *   `consensus.log`: Records consensus grading activities
        *   `email_success.log` and `email_error.log`: Records email sending activities
        *   `pregraded_processing.log`: Records pre-graded Excel file processing
        *   `app.log`: General application logging
        *   `debug.log`: Detailed debug logging when debug mode is enabled
        *   `rate_limit.log`: Records rate limiting activities
    *   Uses `RotatingFileHandler` to prevent log files from growing indefinitely.
    *   Includes request context filtering to add URL and method information to log entries.

6.  **Request Hooks (`before_request` / `after_request`):**
    *   `@app.before_request`:
        *   `start_timer()`: Starts a timer on every request to measure processing duration.
        *   `_enforce_inactivity_timeout()`: Checks the time since the user's last activity and logs them out if the configured limit is exceeded, enhancing security.
        *   `_require_login_everywhere()`: Global authentication guard that protects all routes except public pages (homepage, login, static assets, etc.).
        *   `_global_stack_trace_handler()`: Captures stack traces for all requests in debug mode.
    *   `@app.after_request`:
        *   `log_response()`: Logs detailed information about every response, including the client IP, request method, URL, status code, user agent, and the total processing duration.
        *   `_global_stack_trace_after_handler()`: Logs request completion and performance metrics.

7.  **Template Context Processors:**
    *   `@app.context_processor`:
        *   `inject_default_theme()`: Sets the default theme based on the current blueprint (dark theme for grading, auto for others).
        *   `inject_acl()`: Injects a helper function `current_user_has(*roles)` into all Jinja2 templates. This allows for easy and clean implementation of role-based access control directly within the templates (e.g., `{% if current_user_has('admin') %}`).

8.  **Blueprint Registration:**
    *   The application is organized into modular components using Flask Blueprints. Each blueprint corresponds to a specific feature area.
    *   `create_app()` imports and registers all blueprints, connecting their routes to the main application. The registered blueprints include:
        *   `jobs_bp`: Manages the status and results of background processing jobs.
        *   `uploaded_zips_bp`: Handles ZIP file uploads from Remedio cameras.
        *   `screenings_bp`: Provides interfaces for browsing patient encounter data.
        *   `reports_bp`: Serves PDF reports associated with encounters.
        *   `analytics_bp`: Provides analytics and data visualization interfaces.
        *   `search_bp`: Implements search functionality for images and encounters.
        *   `verify_remedio_glaucoma_bp`: Contains workflows for glaucoma data verification.
        *   `verify_remedio_dr_bp`: Contains workflows for DR data verification.
        *   `verify_remedio_nodr_bp`: Handles verification of cases without DR reports.
        *   `media_bp`: Securely serves image files.
        *   `account_bp`: Handles user self-service account management.
        *   `audit_bp`: Provides data quality assurance tools.
        *   `grading_bp`: The clinical image grading system.
        *   `direct_uploads_bp`: Handles direct image uploads with editing capabilities.
        *   `remedio_zip_uploads_bp`: Processes Remedio ZIP file uploads.
        *   `preprocess_bp`: Handles image preprocessing tasks like anonymization.
        *   `notifications_bp`: Manages user notifications.
        *   `tasks_bp`: Provides task management interfaces for grading workflows.
        *   `ad_hoc_tasks_bp`: Handles ad-hoc task creation for cross-disease grading.
        *   `help_bp`: Provides help documentation and support pages.
        *   `review_bp`: Contains review workflows and discrepancy review functionality.
        *   `auth_bp`: Manages user authentication (login, logout, password reset).
        *   `admin_bp`: Contains all administrative functionalities.
        *   `rate_limit_admin_bp`: Administrative interface for rate limiting configuration.
        *   `dashboard_bp`: Provides dashboard interfaces.
        *   `api_bp`: Provides RESTful API endpoints for programmatic access.
        *   `docs_bp`: Serves documentation pages.

9.  **Error Handling:**
    *   Custom error handlers are defined for common HTTP status codes (`404`, `405`, `500`, `501`) to display user-friendly error pages.
    *   A specific handler for `CSRFError` is included to provide clear feedback to the user when a security check fails, redirecting them to the previous page.
    *   Multiple global exception handlers to capture and log stack traces for debugging purposes.
    *   A generic handler for `HTTPException` ensures that any unhandled HTTP error still results in a gracefully rendered error page.

10. **Core Routes:**
    *   **Homepage (`/`):** Renders the main landing page.
    *   **Favicon (`/favicon.ico`):** Serves the application's favicon.
    *   **Health Check (`/healthz`):** An endpoint for monitoring the application's health. It checks the database connection and returns status information.
    *   **Style Guide (`/style_guide`):** A development route to display and verify the application's visual components and styling.

## Background Task Management

The application includes a background thread for stuck task cleanup:

### `run_stuck_task_cleanup()`
- Runs in a separate daemon thread
- Periodically checks for grading tasks that have been assigned but not completed within the time limit
- Resets stuck tasks to make them available for reassignment
- Runs every 30 minutes with a 60-minute timeout threshold
- Includes error handling to ensure the thread continues running even if errors occur

## Security Features

1. **Session Management:**
   - Server-side sessions with database storage via `DatabaseSessionInterface`
   - Automatic session cleanup for ended sessions with `mark_session_ended()`
   - Inactivity timeout with sliding window
   - Secure cookie settings (HTTPOnly, SameSite, Secure when applicable)

2. **CSRF Protection:**
   - Automatic CSRF token generation and validation via Flask-WTF
   - Custom error handling for CSRF failures with detailed logging
   - Token expiration after 1 hour
   - Enhanced CSRF debugging in development mode

3. **Authentication & Authorization:**
   - Role-based access control (RBAC) with hierarchical roles
   - Global authentication guard with public route exemptions
   - Template helpers for role-based UI rendering via `current_user_has()`
   - Flask-Login integration for user session management

4. **Rate Limiting:**
   - Configurable rate limiting per endpoint
   - Database-backed rate limit storage
   - Custom rate limit admin interface
   - Detailed rate limiting activity logging

5. **Security Middleware:**
   - Payload size validation for request protection
   - File upload security with size and type restrictions
   - Enhanced request logging with security context
   - IP-based locking for failed login attempts

6. **Input Validation:**
   - File upload size limits
   - Content type validation
   - Form validation with WTForms
   - Enhanced request validation middleware

## Running the Application

The `if __name__ == "__main__":` block at the end of the file allows the application to be run directly for development purposes. It:
1. Calls `create_app()` to initialize the application
2. Starts the stuck task cleanup thread
3. Starts the Flask development server with debug mode enabled

### Development
Use `uv run app.py` for development to ensure proper virtual environment usage. The application runs on port 5001 by default.

### Production
For production deployment, use Gunicorn with the provided configuration:
- Application runs on port 5001
- Uses Gunicorn WSGI server with configurable workers
- Database-backed sessions and proper error handling
- Comprehensive logging and monitoring

### Key Application Settings
- **Port**: 5001 (configurable via `PORT` environment variable)
- **Database**: PostgreSQL in production, SQLite for development
- **Package Manager**: Uses `uv` for dependency management
- **Session Storage**: Database-backed sessions via `DatabaseSessionInterface`
- **File Uploads**: Configurable size limits and processing workflows
