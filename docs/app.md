# `app.py` Documentation

This document provides an overview of the `app.py` file, which serves as the main entry point and configuration hub for the Flask web application.

## Core Function: `create_app()`

The primary component of `app.py` is the `create_app()` function, which follows the **Application Factory** pattern. This pattern is a standard practice in Flask that enhances modularity and testability. Instead of creating a global Flask app instance, the app is created and configured within this function.

### Key Responsibilities of `create_app()`:

1.  **Application Initialization and Configuration:**
    *   **Environment Loading:** Loads application settings from a `.env` file using `python-dotenv`. This keeps sensitive data and environment-specific variables out of the source code.
    *   **Flask App Instantiation:** Creates the core `Flask` object.
    *   **Configuration Loading:** Sets up various application configurations, including:
        *   `SECRET_KEY`: For signing session cookies and other security-related needs.
        *   `MAX_CONTENT_LENGTH`: Limits the size of incoming request data.
        *   Session Management: Configures session cookie security (e.g., `HTTPOnly`, `Samesite`) and an automatic inactivity timeout.
        *   `ThreadPoolExecutor`: A pool of threads is initialized and attached to the app config, allowing background tasks to be executed without blocking web requests.

2.  **CSRF Protection:**
    *   Initializes `Flask-WTF`'s `CSRFProtect` extension to guard against Cross-Site Request Forgery attacks on all POST requests.

3.  **Environment and Database Setup:**
    *   Calls `setup_environment()` from `main.py` to ensure that all necessary directories (e.g., for uploads, logs) exist.
    *   Uses SQLAlchemy to create all database tables defined in `models.py` via `Base.metadata.create_all(engine)`.
    *   **Role-Based Access Control (RBAC):** Seeds the database with a predefined set of user roles (e.g., 'admin', 'user') by calling `ensure_roles()`. This is an idempotent operation, meaning it can be run safely multiple times.

4.  **Logging:**
    *   Configures robust logging for HTTP requests.
    *   Two separate log files are created in the `logs/` directory:
        *   `http_success.log`: Records all successful requests (status codes `< 400`).
        *   `http_error.log`: Records all client and server errors (status codes `>= 400`).
    *   Uses `RotatingFileHandler` to prevent log files from growing indefinitely.

5.  **Request Hooks:**
    *   `@app.before_request`:
        *   Starts a timer to measure request processing duration.
        *   Enforces an inactivity timeout by checking the time since the user's last activity and logging them out if the limit is exceeded.
    *   `@app.after_request`:
        *   Logs detailed information about every response, including the client IP, request method, URL, status code, user agent, and processing duration.

6.  **Template Context Processor:**
    *   `@app.context_processor`:
        *   Injects a helper function `current_user_has(*roles)` into all Jinja2 templates. This allows for easy and clean implementation of role-based access control directly within the templates (e.g., `{% if current_user_has('admin') %}`).

7.  **Blueprint Registration:**
    *   The application is organized into modular components using Flask Blueprints. Each blueprint corresponds to a specific feature area (e.g., authentication, file uploads, job status).
    *   `create_app()` imports and registers all blueprints, connecting their routes to the main application. The registered blueprints include:
        *   `uploads_bp`: Handles file uploads.
        *   `jobs_bp`: Manages job status and results.
        *   `auth_bp`: User authentication (login, logout).
        *   `admin_bp`: Admin-specific functionalities.
        *   And others for screenings, reports, etc.

8.  **Authentication and Authorization:**
    *   Initializes the `Flask-Login` extension for managing user sessions.
    *   A global `@app.before_request` hook (`_require_login_everywhere`) is registered to protect all routes by default, redirecting unauthenticated users to the login page. A few pages like the homepage and login page are explicitly excluded from this guard.

9.  **Error Handling:**
    *   Custom error handlers are defined for common HTTP status codes (`404`, `405`, `500`, etc.) to display user-friendly error pages.
    *   A specific handler for `CSRFError` is included to provide clear feedback to the user when a security check fails.
    *   A generic handler for `HTTPException` ensures that any unhandled HTTP error still results in a gracefully rendered error page.

10. **Core Routes:**
    *   **Homepage (`/`):** Renders the main landing page, which displays summary statistics like the total number of processed images and screenings.
    *   **Health Check (`/healthz`):** An endpoint for monitoring the application's health. It checks the database connection and returns the status of processing jobs.
    *   **Style Guide (`/style_guide`):** A development route to display and verify the application's visual components and styling.

## Running the Application

The `if __name__ == "__main__":` block at the end of the file allows the application to be run directly for development purposes. It calls `create_app()` and then starts the Flask development server.

For a production environment, a more robust WSGI server like Gunicorn or uWSGI should be used instead of the built-in development server.