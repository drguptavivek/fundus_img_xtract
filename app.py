# app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, current_app, jsonify, render_template, request, redirect, url_for, session, flash
from flask import send_from_directory
from flask_cors import CORS
from models import Base, Job, Session, engine
from zip_processor import setup_environment
from dotenv import load_dotenv  
import time
from datetime import timedelta
import threading
import atexit

from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from utils.datetime_filters import format_user_datetime
from utils.timezone_choices import DEFAULT_TIMEZONE
from server_side_session import DatabaseSessionInterface, mark_session_ended


csrf = CSRFProtect()

def create_app():
    load_dotenv()
    app = Flask(
        __name__,
        static_folder="static",         # default, explicit for clarity
        static_url_path="/static"       # default path)
    )

    # Static cache age (seconds) — tweak per env
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = int(os.getenv("STATIC_MAX_AGE", 60 * 60 * 24 * 7))  # 7 days
    app.config["ASSETS_VERSION"] = os.getenv("ASSETS_VERSION", "")

    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

    app.config.setdefault(
        "DEFAULT_DISPLAY_TIMEZONE",
        os.getenv("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
    )
    app.jinja_env.filters["user_datetime"] = format_user_datetime

    @app.context_processor
    def inject_default_theme():
        from flask import request
        default_theme = "dark" if request.blueprint == "grading" else "auto"
        return {"default_theme": default_theme}

    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
    app.config["PER_FILE_MAX_BYTES"] = int(os.getenv("PER_FILE_MAX_BYTES", 10 * 1024 * 1024))
    app.config["MAX_FILES_PER_UPLOAD"] = int(os.getenv("MAX_FILES_PER_UPLOAD", 50))
    app.config["WORKERS"] = int(os.getenv("WORKERS", "4"))
    app.config["UPLOADED_RESULTS_PAGE_SIZE"] = int(os.getenv("UPLOADED_RESULTS_PAGE_SIZE", 50))
    app.config["SCREENINGS_PAGE_SIZE"] = int(os.getenv("SCREENINGS_PAGE_SIZE", 50))
    app.config["EMAIL_DEBUG_LOGGING"] = str(os.getenv("EMAIL_DEBUG_LOGGING", "false")).lower() in ("1", "true", "yes")
    app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER")
    smtp_port_env = os.getenv("SMTP_PORT")
    app.config["SMTP_PORT"] = int(smtp_port_env) if smtp_port_env and smtp_port_env.isdigit() else None
    app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME")
    app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD")
    app.config["FROM_EMAIL"] = os.getenv("FROM_EMAIL")

   # Session cookie hygiene
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
        SESSION_COOKIE_SECURE=str(os.getenv("SESSION_COOKIE_SECURE", "false")).lower() == "true",
    )
    # --- Inactivity timeout (sliding) ---
    app.config["INACTIVITY_TIMEOUT_MINUTES"] = int(os.getenv("INACTIVITY_TIMEOUT_MINUTES", 30))
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta( minutes=app.config["INACTIVITY_TIMEOUT_MINUTES"])
    # refresh cookie each request (sliding window)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    # Thread pool (shared via app.config)
    app.config["EXECUTOR"] = ThreadPoolExecutor(max_workers=app.config["WORKERS"])


    app.config["WTF_CSRF_TIME_LIMIT"] = 60 * 60  # 1 hour
    # app.config["WTF_CSRF_CHECK_DEFAULT"] = True  # default True

    csrf.init_app(app)
    app.session_interface = DatabaseSessionInterface()
    
    # Initialize CORS for API endpoints
    # Allow credentials from same origin (localhost/127.0.0.1) to handle session cookies
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
            "supports_credentials": True
        }
    }, supports_credentials=True)

    # Ensure folders + schema (idempotent)
    setup_environment()
    Base.metadata.create_all(engine)

    # --- RBAC: seed core roles once ---
    from sqlalchemy.orm import sessionmaker
    from auth.roles import ensure_roles, DEFAULT_ROLES
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as db:
        ensure_roles(db, DEFAULT_ROLES)
        # Ensure core diseases are always present
        

    # ---------------- Logging Configuration ----------------
    from pathlib import Path

    log_root_setting = app.config.get("LOG_DIR") or os.getenv("LOG_DIR")
    log_dir = Path(log_root_setting or (Path(__file__).resolve().parent / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    debug_mode = bool(app.debug or app.config.get("ENABLE_DEBUG_LOGGING", False))
    log_max_bytes = int(app.config.get("LOG_MAX_BYTES", 2 * 1024 * 1024))
    log_backup_count = int(app.config.get("LOG_BACKUP_COUNT", 5))

    class RequestContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            record.url = "-"
            record.method = "-"
            try:
                record.url = request.url  # type: ignore[attr-defined]
                record.method = request.method  # type: ignore[attr-defined]
            except Exception:
                pass
            return True

    request_filter = RequestContextFilter()

    def make_handler(filename: str, level: int, formatter: logging.Formatter, *, filters: list[logging.Filter] | None = None) -> logging.Handler:
        handler = RotatingFileHandler(log_dir / filename, maxBytes=log_max_bytes, backupCount=log_backup_count, encoding="utf-8", delay=True)
        handler.setLevel(level)
        handler.setFormatter(formatter)
        for flt in filters or []:
            handler.addFilter(flt)
        return handler

    def configure_logger(name: str, level: int, handler: logging.Handler, extra_handlers: list[logging.Handler] | None = None) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        for existing in list(logger.handlers):
            logger.removeHandler(existing)
            try:
                existing.close()
            except Exception:
                pass
        logger.addHandler(handler)
        for extra in extra_handlers or []:
            logger.addHandler(extra)
        return logger

    base_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s")
    detailed_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d %(message)s")
    http_error_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s url=%(url)s %(message)s")

    http_error_handler = make_handler("http_error.log", logging.WARNING, http_error_format, filters=[request_filter])
    runtime_error_handler = make_handler("runtime_error.log", logging.ERROR, detailed_format)
    grades_handler = make_handler("grades.log", logging.INFO, base_format)
    pregraded_processing_handler = make_handler("pregraded_processing.log", logging.INFO, base_format)
    auth_handler = make_handler("auth.log", logging.INFO, base_format)
    editing_handler = make_handler("editing.log", logging.INFO, base_format)
    consensus_handler = make_handler("consensus.log", logging.INFO, base_format)
    email_success_handler = make_handler("email_success.log", logging.INFO, base_format)
    email_error_handler = make_handler("email_error.log", logging.ERROR, detailed_format)
    app_handler = make_handler("app.log", logging.INFO, base_format)

    debug_handler = None
    console_handler = None
    if debug_mode:
        debug_handler = make_handler("debug.log", logging.DEBUG, detailed_format)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(detailed_format)

    http_error_logger = configure_logger("http_error", logging.WARNING, http_error_handler)
    runtime_error_logger = configure_logger("runtime_error", logging.ERROR, runtime_error_handler)
    grades_logger = configure_logger("grades", logging.INFO, grades_handler)
    pregraded_processing_logger = configure_logger("pregraded_processing", logging.INFO, pregraded_processing_handler)
    auth_logger = configure_logger("auth", logging.INFO, auth_handler)
    editing_logger = configure_logger("editing", logging.INFO, editing_handler)
    consensus_logger = configure_logger("consensus", logging.INFO, consensus_handler)
    email_success_logger = configure_logger("email_success", logging.INFO, email_success_handler)
    email_error_logger = configure_logger("email_error", logging.ERROR, email_error_handler)

    if app.config.get("EMAIL_DEBUG_LOGGING"):
        email_debug_handler = make_handler("email_debug.log", logging.DEBUG, detailed_format)
        configure_logger("email_debug", logging.DEBUG, email_debug_handler)
    else:
        email_debug_logger = logging.getLogger("email_debug")
        for existing in list(email_debug_logger.handlers):
            email_debug_logger.removeHandler(existing)
            try:
                existing.close()
            except Exception:
                pass
        email_debug_logger.handlers = []

    extra_app_handlers: list[logging.Handler] = []
    if debug_handler is not None:
        debug_logger = configure_logger("debug", logging.DEBUG, debug_handler, extra_handlers=[console_handler] if console_handler else None)
        extra_app_handlers.append(debug_handler)
        if console_handler:
            extra_app_handlers.append(console_handler)
    else:
        debug_logger = configure_logger("debug", logging.INFO, app_handler)

    app_logger = configure_logger("app", logging.DEBUG if debug_mode else logging.INFO, app_handler, extra_handlers=extra_app_handlers)

    app.logger.handlers = []
    app.logger.setLevel(app_logger.level)
    for handler in app_logger.handlers:
        app.logger.addHandler(handler)
    app.logger.propagate = False

    grades_logger.info("Grades logger initialized at %s", str(log_dir / "grades.log"))
    pregraded_processing_logger.info("Pregraded processing logger initialized at %s", str(log_dir / "pregraded_processing.log"))
    auth_logger.info("Auth logger initialized at %s", str(log_dir / "auth.log"))
    editing_logger.info("Editing logger initialized at %s", str(log_dir / "editing.log"))
    consensus_logger.info("Consensus logger initialized at %s", str(log_dir / "consensus.log"))
    email_success_logger.info("Email success logger initialized at %s", str(log_dir / "email_success.log"))
    email_error_logger.info("Email error logger initialized at %s", str(log_dir / "email_error.log"))
    runtime_error_logger.info("Runtime error logger initialized at %s", str(log_dir / "runtime_error.log"))

    # Expose a template helper: {{ current_user_has('admin') }}
    @app.context_processor
    def inject_acl():
        from flask_login import current_user as cu
        def current_user_has(*roles):
            try:
                return cu.is_authenticated and cu.has_role(*roles)
            except Exception:
                return False
        return dict(current_user_has=current_user_has)


    @app.before_request
    def start_timer():
        request.start_time = time.time()

    # Inactivity auto-logout (must be registered before the global auth guard)
    @app.before_request
    def _enforce_inactivity_timeout():
        from flask_login import current_user, logout_user
        # skip static & login
        p = request.path or "/"
        if p.startswith("/static/") or p == "/login":
            return
        if not current_user.is_authenticated:
            return
        # check idle time
        try:
            last = int(session.get("last_active", 0))
        except Exception:
            last = 0
        import time as _t
        now = int(_t.time())
        timeout_s = app.config.get("INACTIVITY_TIMEOUT_MINUTES", 30) * 60
        if last and (now - last) > timeout_s:
            # Log session timeout
            from flask_login import current_user
            from auth.utils import get_client_ip
            username = getattr(current_user, 'username', 'Unknown') if current_user.is_authenticated else 'Unknown'
            ip = get_client_ip()
            auth_logger = logging.getLogger("auth")
            auth_logger.info(f"Session timeout - User: {username}, IP: {ip}, Last active: {last}, Timeout duration: {timeout_s // 60} minutes")
            
            cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
            prior_session_id = getattr(session, "session_id", None) or request.cookies.get(cookie_name)
            try:
                session_user_id = int(current_user.get_id())  # type: ignore[arg-type]
            except (TypeError, ValueError):
                session_user_id = None
            logout_user()
            session.clear()
            session.modified = True
            mark_session_ended(prior_session_id, session_user_id)
            flash(f"Session expired after {timeout_s // 60} minutes of inactivity.", "warning")
            return redirect(url_for("auth.login"))
        session["last_active"] = now
        session.modified = True

    @app.after_request
    def log_response(response):
        # Duration in ms
        duration_ms = None
        if hasattr(request, "start_time"):
            duration_ms = int((time.time() - request.start_time) * 1000)

        # Get client IP (prefer X-Forwarded-For if present from proxy)
        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        client_ip = forwarded_for or request.remote_addr or "-"

        # User agent
        ua = request.headers.get("User-Agent", "-")

        # Full URL
        full_url = request.url

        # Build log line
        line = (
            f"{client_ip} {request.method} {full_url} "
            f"{response.status_code} "
            f"UA={ua} "
            f"duration={duration_ms if duration_ms is not None else '-'}ms"
        )

        if response.status_code >= 400:
            http_error_logger.warning(line)

        return response

    #  relative imports
    from jobs import jobs_bp
    app.register_blueprint(jobs_bp)
    
    from uploaded_zips import bp as uploaded_zips_bp
    app.register_blueprint(uploaded_zips_bp)

    from screenings import bp as screenings_bp
    app.register_blueprint(screenings_bp)

    from reports import bp as reports_bp
    app.register_blueprint(reports_bp)

    from analytics import bp as analytics_bp
    app.register_blueprint(analytics_bp)

    from search import bp as search_bp
    app.register_blueprint(search_bp)

    from verify_remedio_glaucoma import bp as verify_remedio_glaucoma_bp
    app.register_blueprint(verify_remedio_glaucoma_bp)

    # DR blueprint removed as it's no longer needed

    from verify_remedio_dr import bp as verify_remedio_dr_bp
    app.register_blueprint(verify_remedio_dr_bp)

    from verify_remedio_nodr import bp as verify_remedio_nodr_bp
    app.register_blueprint(verify_remedio_nodr_bp)

    from media import bp as media_bp
    app.register_blueprint(media_bp)

    from account import account_bp
    app.register_blueprint(account_bp)

    from audit import bp as audit_bp
    app.register_blueprint(audit_bp)

    from grading import bp as grading_bp
    app.register_blueprint(grading_bp)

    from direct_uploads import bp as direct_uploads_bp
    app.register_blueprint(direct_uploads_bp)

    from remedio_zip_uploads import bp as remedio_zip_uploads_bp
    app.register_blueprint(remedio_zip_uploads_bp)

    from preprocess import bp as preprocess_bp
    app.register_blueprint(preprocess_bp)

    from notifications import bp as notifications_bp
    app.register_blueprint(notifications_bp)

    from api.gradings import bp as api_gradings_bp
    app.register_blueprint(api_gradings_bp)

    from tasks import bp as tasks_bp
    app.register_blueprint(tasks_bp)

    from help import bp as help_bp
    app.register_blueprint(help_bp)

    from review import bp as review_bp
    app.register_blueprint(review_bp)

        # -------- Auth blueprint + Flask-Login --------
    # (Requires the auth/ package provided earlier)
    from auth.routes import auth_bp, login_manager
    app.register_blueprint(auth_bp)            # /login, /logout
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Global guard: require login for everything except login page, static, favicon
    @app.before_request
    def _require_login_everywhere():
        from flask_login import current_user, logout_user
        path = request.path or "/"

        # Detect stale client sessions (e.g., after server restart with old cookie)
        try:
            has_client_session = bool(session.get("_user_id"))
        except Exception:
            has_client_session = False

        if has_client_session and not current_user.is_authenticated:
            cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
            prior_session_id = getattr(session, "session_id", None) or request.cookies.get(cookie_name)
            logout_user()
            session.clear()
            session.modified = True
            mark_session_ended(prior_session_id)

        if (
            path == "/"
            or path == "/login"
            or path.startswith("/static/")
            or path == "/favicon.ico"
            or path == "/style_guide"
            or path== "/forgot-password"
            or path == "/reset-password"
            or path == "/check-email-status"
            or path == "/email-sse"
            or path.startswith("/docs/")
            or path.startswith("/help/")
        ):
            return  # allowed without auth
        if not current_user.is_authenticated:
            # Clear any stale session to avoid repeated forbidden responses
            prior_session_id = getattr(session, "session_id", None)
            session.clear()
            session.modified = True
            mark_session_ended(prior_session_id)
            return redirect(url_for("auth.login"))
        if getattr(current_user, "is_active", True) is False:
            cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
            prior_session_id = getattr(session, "session_id", None) or request.cookies.get(cookie_name)
            try:
                session_user_id = int(current_user.get_id())  # type: ignore[arg-type]
            except (TypeError, ValueError):
                session_user_id = None
            logout_user()
            session.clear()
            session.modified = True
            mark_session_ended(prior_session_id, session_user_id)
            flash("Your account is inactive. Please contact an administrator.", "warning")
            return redirect(url_for("auth.login"))

    # Global stack trace handler - captures stack traces for all requests
    @app.before_request
    def _global_stack_trace_handler_alt():
        """Global handler to capture stack traces for all requests in debug mode."""
        # Store request start time for performance tracking
        import time
        request._start_time = time.time()
        
        # Log the incoming request in debug mode
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        if runtime_logger.isEnabledFor(logging.DEBUG):
            from utils.stack_trace_handler import log_current_stack
            log_current_stack(f"Processing request: {request.method} {request.url}")

    @app.after_request
    def _global_stack_trace_after_handler_alt(response):
        """Global handler to capture performance and completion info for all requests."""
        import time
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        
        # Calculate request duration
        duration = None
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            
        # Log completion in debug mode
        if runtime_logger.isEnabledFor(logging.DEBUG):
            runtime_logger.debug(
                f"Request completed: {request.method} {request.url} "
                f"Status: {response.status_code} Duration: {duration:.3f}s"
            )
            
        return response

    # Global exception handler - captures stack traces for all unhandled exceptions
    @app.errorhandler(Exception)
    def _global_exception_handler_alt(e):
        """Global handler to capture stack traces for all unhandled exceptions."""
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        
        # Log the exception with full stack trace
        from utils.stack_trace_handler import log_stack_trace
        log_stack_trace(
            message=f"Global exception handler caught: {type(e).__name__}",
            exception=e
        )
        
        # Also log to the standard app logger
        current_app.logger.exception("Unhandled exception in request: %s", e)
        
        # Don't re-raise here as this is meant to be the catch-all handler
        return render_template("errors/500.html"), 500

    from admin import admin_bp
    app.register_blueprint(admin_bp)

    from dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from api import api_bp
    app.register_blueprint(api_bp)

    from docs import docs_bp
    app.register_blueprint(docs_bp)




    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash(e.description or "Security check failed. Please try again.", "danger")
        # send them back or home
        return redirect(request.referrer or url_for("homepage")), 400

    # ---- Custom error pages ----
    @app.errorhandler(404)
    def handle_404(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(405)
    def handle_405(e):
        return render_template("errors/405.html"), 405

    @app.errorhandler(501)
    def handle_501(e):
        return render_template("errors/501.html"), 501

    @app.errorhandler(500)
    def handle_500(e):
        current_app.logger.exception("Unhandled exception: %s", e)
        # Log the stack trace using our stack trace handler
        from utils.stack_trace_handler import log_stack_trace
        log_stack_trace(
            message="500 Internal Server Error",
            exception=e
        )
        return render_template("errors/500.html"), 500

    @app.errorhandler(Exception)
    def handle_generic_exception(e):
        """Handle any unhandled exceptions globally."""
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        
        # Log the exception with full stack trace
        from utils.stack_trace_handler import log_stack_trace
        log_stack_trace(
            message=f"Unhandled exception: {type(e).__name__}",
            exception=e
        )
        
        # Also log to the standard app logger
        current_app.logger.exception("Unhandled exception: %s", e)
        
        # Return a generic error response
        return render_template("errors/500.html"), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        # Fallback renderer for HTTP errors without a dedicated template
        return (
            render_template(
                "errors/error.html",
                code=getattr(e, "code", 500),
                title=getattr(e, "name", "Error"),
                message=getattr(e, "description", "An unexpected error occurred."),
            ),
            getattr(e, "code", 500),
        )

    # Global stack trace handler - captures stack traces for all requests
    @app.before_request
    def _global_stack_trace_handler():
        """Global handler to capture stack traces for all requests in debug mode."""
        # Store request start time for performance tracking
        import time
        request._start_time = time.time()
        
        # Log the incoming request in debug mode
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        if runtime_logger.isEnabledFor(logging.DEBUG):
            from utils.stack_trace_handler import log_current_stack
            log_current_stack(f"Processing request: {request.method} {request.url}")

    @app.after_request
    def _global_stack_trace_after_handler(response):
        """Global handler to capture performance and completion info for all requests."""
        import time
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        
        # Calculate request duration
        duration = None
        if hasattr(request, '_start_time'):
            duration = time.time() - request._start_time
            
        # Log completion in debug mode
        if runtime_logger.isEnabledFor(logging.DEBUG):
            runtime_logger.debug(
                f"Request completed: {request.method} {request.url} "
                f"Status: {response.status_code} Duration: {duration:.3f}s"
            )
            
        return response

    # Global exception handler - captures stack traces for all unhandled exceptions
    @app.errorhandler(Exception)
    def _global_exception_handler(e):
        """Global handler to capture stack traces for all unhandled exceptions."""
        import logging
        runtime_logger = logging.getLogger("runtime_error")
        
        # Log the exception with full stack trace
        from utils.stack_trace_handler import log_stack_trace
        log_stack_trace(
            message=f"Global exception handler caught: {type(e).__name__}",
            exception=e
        )
        
        # Also log to the standard app logger
        current_app.logger.exception("Unhandled exception in request: %s", e)
        
        # Don't re-raise here as this is meant to be the catch-all handler
        return render_template("errors/500.html"), 500

    # Serve classic /favicon.ico path for browsers that request it directly
    @app.get('/favicon.ico')
    def _favicon():
        return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

    # -------------------------------
    # New homepage route
    @app.route("/")
    def homepage():
        from home import homepage as home_page
        return home_page()
    # -------------------------------

    # -------------------------------
    # Style Guide
    @app.route("/style_guide")
    def style_guide():
        return render_template("style_guide.html")
    # -------------------------------

    @app.route("/healthz", methods=["GET"])
    def healthz():
        db = Session()
        try:
            total = db.query(Job).count()
            queued = db.query(Job).filter(Job.status == "queued").count()
            processing = db.query(Job).filter(Job.status == "processing").count()
            errors = db.query(Job).filter(Job.status == "error").count()
            return jsonify({
                "status": "ok"
                }
            )
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        finally:
            db.close()

    return app


def run_stuck_task_cleanup():
    """
    Run the stuck task cleanup function periodically to identify and reset tasks
    that have been assigned but not completed within the time limit.
    """
    from utils.dualGradingStuckTaskCleanup import reset_stuck_tasks
    
    while True:
        try:
            # Run the cleanup every 30 minutes
            cleaned_count = reset_stuck_tasks(time_limit_minutes=60)
            if cleaned_count > 0:
                print(f"Reset {cleaned_count} stuck tasks")
            
            # Sleep for 30 minutes before the next run
            time.sleep(30 * 60)
        except Exception as e:
            import logging
            logging.error(f"Error in stuck task cleanup thread: {str(e)}")
            # Even if an error occurs, keep the thread running by sleeping a bit before continuing
            time.sleep(5 * 60)  # Wait 5 minutes before retrying


if __name__ == "__main__":
    app = create_app()
    
    # Start the stuck task cleanup thread
    import threading
    cleanup_thread = threading.Thread(target=run_stuck_task_cleanup, daemon=True)
    cleanup_thread.start()
    
    # dev server; for prod use gunicorn/uwsgi
    app.run(debug=True, host="127.0.0.1", port=5001)
