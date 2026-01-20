# app.py
import os
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, current_app, jsonify, render_template, request, redirect, url_for, session, flash
from flask import send_from_directory
from flask import message_flashed
from flask_cors import CORS
from models import Base, Job, Session, engine
from zip_processor import setup_environment
import time
from datetime import timedelta
import threading
import atexit

from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from utils.datetime_filters import format_user_datetime
from utils.timezone_choices import DEFAULT_TIMEZONE
from server_side_session import DatabaseSessionInterface, mark_session_ended
from utils.rate_limiter import init_rate_limiting, rate_limit
from utils.rate_limiter import init_rate_limiting, rate_limit
from utils.security_middleware import PayloadSizeValidator, is_safe_url
from utils.env_loader import load_environment
from utils.env_loader import get_env
from utils.redis_connection import build_redis_url
from utils.log_sanitize import sanitize_log_value, sanitize_log_headers
from app_init.logging_config import configure_logging
from app_init.security_headers import register_csp
from app_init.startup_checks import run_startup_env_checks
from app_cache import cache
from utils.db_query_logger import init_db_query_logger


csrf = CSRFProtect()


def _env_bool(key: str, default: str = "false") -> bool:
    """Parse a boolean environment variable with sane defaults."""
    return str(os.getenv(key, default)).lower() in ("1", "true", "yes")


def _env_domain(key: str) -> str | None:
    """Return an optional cookie domain, treating empty/none-like values as unset."""
    value = os.getenv(key)
    if value and value.lower() not in ("none", "null"):
        return value
    return None


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:5001", "http://127.0.0.1:5001"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _configure_base_settings(app: Flask) -> None:
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = int(os.getenv("STATIC_MAX_AGE", 60 * 60 * 24 * 7))
    app.config["ASSETS_VERSION"] = os.getenv("ASSETS_VERSION", "")
    app.config["BASE_URL"] = (get_env("BASE_URL") or "").rstrip("/")
    app.config.setdefault("CACHE_TYPE", "RedisCache")
    app.config.setdefault("CACHE_REDIS_URL", os.getenv("CACHE_REDIS_URL") or build_redis_url())
    app.config.setdefault("CACHE_DEFAULT_TIMEOUT", 15 * 60)
    app.config.setdefault("CACHE_KEY_PREFIX", os.getenv("CACHE_KEY_PREFIX", "fim:cache:"))
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    app.config.setdefault(
        "DEFAULT_DISPLAY_TIMEZONE",
        os.getenv("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE),
    )
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 1024 * 1024 * 1024))
    app.config["PER_FILE_MAX_BYTES"] = int(os.getenv("PER_FILE_MAX_BYTES", 10 * 1024 * 1024))
    app.config["MAX_FILES_PER_UPLOAD"] = int(os.getenv("MAX_FILES_PER_UPLOAD", 50))
    app.config["WORKERS"] = int(os.getenv("WORKERS", "4"))
    app.config["UPLOADED_RESULTS_PAGE_SIZE"] = int(os.getenv("UPLOADED_RESULTS_PAGE_SIZE", 50))
    app.config["SCREENINGS_PAGE_SIZE"] = int(os.getenv("SCREENINGS_PAGE_SIZE", 50))
    app.config["EMAIL_DEBUG_LOGGING"] = _env_bool("EMAIL_DEBUG_LOGGING", "false")
    app.config["SMTP_SERVER"] = os.getenv("SMTP_SERVER")
    smtp_port_env = os.getenv("SMTP_PORT")
    app.config["SMTP_PORT"] = int(smtp_port_env) if smtp_port_env and smtp_port_env.isdigit() else None
    app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME")
    app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD")
    app.config["FROM_EMAIL"] = os.getenv("FROM_EMAIL")
    app.config["SMTP_USE_SSL"] = _env_bool("SMTP_USE_SSL", "false")
    app.config["DB_QUERY_LOGGING"] = _env_bool("DB_QUERY_LOGGING", "false")
    app.config["MATERIALIZED_VIEW_SCHEDULE_ENABLED"] = _env_bool("MATERIALIZED_VIEW_SCHEDULE_ENABLED", "true")
    app.config["MATERIALIZED_VIEW_SCHEDULE_TIMES"] = os.getenv(
        "MATERIALIZED_VIEW_SCHEDULE_TIMES",
        ",".join([f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]),
    ).split(",")
    app.config["MATERIALIZED_VIEW_TIMEZONE"] = os.getenv(
        "MATERIALIZED_VIEW_TIMEZONE", app.config["DEFAULT_DISPLAY_TIMEZONE"]
    )
    app.config["MATERIALIZED_VIEW_RETRY_ATTEMPTS"] = int(os.getenv("MATERIALIZED_VIEW_RETRY_ATTEMPTS", "3"))
    app.config["MATERIALIZED_VIEW_RETRY_DELAY_SECONDS"] = int(
        os.getenv("MATERIALIZED_VIEW_RETRY_DELAY_SECONDS", "60")
    )
    app.config["THUMBNAIL_MAINTENANCE_ENABLED"] = _env_bool("THUMBNAIL_MAINTENANCE_ENABLED", "false")
    app.config["THUMBNAIL_MAINTENANCE_TIMEZONE"] = os.getenv(
        "THUMBNAIL_MAINTENANCE_TIMEZONE", app.config["DEFAULT_DISPLAY_TIMEZONE"]
    )
    app.config["THUMBNAIL_MAINTENANCE_SCHEDULE_TIMES"] = os.getenv(
        "THUMBNAIL_MAINTENANCE_SCHEDULE_TIMES",
        "02:30,07:00,13:30,19:00,01:30",
    ).split(",")
    app.config["THUMBNAIL_MAINTENANCE_CLEANUP_LIMIT"] = int(
        os.getenv("THUMBNAIL_MAINTENANCE_CLEANUP_LIMIT", "1000")
    )
    app.config["THUMBNAIL_MAINTENANCE_REGENERATION_LIMIT"] = int(
        os.getenv("THUMBNAIL_MAINTENANCE_REGENERATION_LIMIT", "100")
    )
    app.config["THUMBNAIL_MAINTENANCE_VALIDATION_SAMPLE_SIZE"] = int(
        os.getenv("THUMBNAIL_MAINTENANCE_VALIDATION_SAMPLE_SIZE", "200")
    )
    app.config["THUMBNAIL_MAINTENANCE_LOG_LEVEL"] = os.getenv("THUMBNAIL_MAINTENANCE_LOG_LEVEL", "INFO")
    app.config["WTF_CSRF_TIME_LIMIT"] = 60 * 60
    app.config["CORS_ALLOWED_ORIGINS"] = _parse_cors_origins()


def _register_template_filters(app: Flask) -> None:
    app.jinja_env.filters["user_datetime"] = format_user_datetime

    def from_json(value):
        import json
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    app.jinja_env.filters["from_json"] = from_json

    from utils.log_sanitize import mask_text_emails
    app.jinja_env.filters["mask_text_emails"] = mask_text_emails


def _register_default_theme_context(app: Flask) -> None:
    @app.context_processor
    def inject_default_theme():
        from flask import request
        default_theme = "dark" if request.blueprint == "grading" else "auto"
        return {"default_theme": default_theme}


def _configure_session_and_proxy(app: Flask) -> bool:
    app.config.update(
        SESSION_COOKIE_HTTPONLY=_env_bool("SESSION_COOKIE_HTTPONLY", "true"),
        SESSION_COOKIE_SAMESITE=os.getenv("SESSION_COOKIE_SAMESITE", "Lax"),
        SESSION_COOKIE_SECURE=_env_bool("SESSION_COOKIE_SECURE", "false"),
        SESSION_COOKIE_PATH=os.getenv("SESSION_COOKIE_PATH", "/"),
        SESSION_COOKIE_DOMAIN=_env_domain("SESSION_COOKIE_DOMAIN"),
        SESSION_COOKIE_NAME=os.getenv("SESSION_COOKIE_NAME", "session"),
        PREFERRED_URL_SCHEME=os.getenv(
            "PREFERRED_URL_SCHEME",
            "https" if _env_bool("FORCE_HTTPS", "false") else "http",
        ),
    )
    app.config["INACTIVITY_TIMEOUT_MINUTES"] = int(os.getenv("INACTIVITY_TIMEOUT_MINUTES", 30))
    app.config["INACTIVITY_WARNING_LEAD_MINUTES"] = int(os.getenv("INACTIVITY_WARNING_LEAD_MINUTES", 2))
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=app.config["INACTIVITY_TIMEOUT_MINUTES"])
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True
    force_https = _env_bool("FORCE_HTTPS", "false")
    proxy_hops = int(os.getenv("TRUST_PROXY_HOPS", "1"))
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=proxy_hops,
        x_proto=proxy_hops,
        x_host=proxy_hops,
        x_prefix=proxy_hops,
    )
    return force_https


def _configure_executors(app: Flask) -> None:
    app.config["EXECUTOR"] = ThreadPoolExecutor(max_workers=app.config["WORKERS"])


def _register_csrf_protection(app: Flask) -> None:
    def csrf_protect():
        auth_logger = logging.getLogger("auth")
        if not auth_logger.isEnabledFor(logging.DEBUG):
            return None
        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            auth_logger.debug(
                "CSRF Check - Method: %s, Path: %s",
                sanitize_log_value(request.method),
                sanitize_log_value(request.path),
            )
            auth_logger.debug(f"CSRF Check - Form has CSRF token: {'csrf_token' in request.form}")
            auth_logger.debug(f"CSRF Check - Headers have CSRF token: {'X-CSRFToken' in request.headers}")

            try:
                session_keys = list(session.keys()) if session else []
                auth_logger.debug(
                    "CSRF Check - Session keys: %s",
                    sanitize_log_value(session_keys),
                )
                if 'csrf_token' in session:
                    auth_logger.debug(f"CSRF Check - Session CSRF token exists: True")
                else:
                    auth_logger.debug(f"CSRF Check - Session CSRF token exists: False")

                if hasattr(session, 'session_id'):
                    auth_logger.debug(
                        "CSRF Check - Session ID: %s",
                        sanitize_log_value(session.session_id),
                    )

                cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
                session_cookie = request.cookies.get(cookie_name)
                auth_logger.debug(
                    "CSRF Check - Session cookie exists: %s",
                    sanitize_log_value(session_cookie is not None),
                )
                if session_cookie:
                    auth_logger.debug(
                        "CSRF Check - Session cookie value: %s",
                        sanitize_log_value(session_cookie[:50]),
                    )

            except Exception as e:
                auth_logger.error(
                    "CSRF Check - Error checking session: %s",
                    sanitize_log_value(e),
                )

            if request.form:
                auth_logger.debug(
                    "CSRF Check - Form keys: %s",
                    sanitize_log_value(list(request.form.keys())),
                )
                if 'csrf_token' in request.form:
                    auth_logger.debug(
                        "CSRF Check - Form CSRF token value: %s",
                        sanitize_log_value(request.form["csrf_token"][:50]),
                    )
            if request.headers:
                csrf_headers = {k: v for k, v in request.headers.items() if 'csrf' in k.lower()}
                auth_logger.debug(
                    "CSRF Check - CSRF Headers: %s",
                    sanitize_log_value(csrf_headers),
                )

    app.before_request(csrf_protect)
    csrf.init_app(app)


def _register_https_redirect(app: Flask) -> None:
    @app.before_request
    def _redirect_insecure_requests():
        """Force HTTPS to avoid dropping secure cookies/CSRF tokens behind a proxy."""
        if request.path in ("/healthz", "/healthz/"):
            return None
        if request.is_secure:
            return None
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
        if forwarded_proto == "https":
            return None
        https_url = request.url.replace("http://", "https://", 1)
        return redirect(https_url, code=301)


def _initialize_middleware(app: Flask) -> None:
    init_rate_limiting(app)
    PayloadSizeValidator(app)
    cors_origins = app.config.get("CORS_ALLOWED_ORIGINS", [])
    cors_resources = {
        r"/api/*": {"origins": cors_origins, "supports_credentials": True},
        r"/check-email-status": {"origins": cors_origins, "supports_credentials": True},
        r"/email-sse": {"origins": cors_origins, "supports_credentials": True},
        r"/check-session": {"origins": cors_origins, "supports_credentials": True},
    }
    CORS(app, resources=cors_resources, supports_credentials=True)


def _ensure_core_roles() -> None:
    from sqlalchemy.orm import sessionmaker
    from auth.roles import ensure_roles, DEFAULT_ROLES
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as db:
        ensure_roles(db, DEFAULT_ROLES)


def _configure_logging_services(app: Flask) -> dict[str, logging.Logger]:
    loggers = configure_logging(app)
    init_db_query_logger(app, engine)
    return loggers


def _run_startup_checks(app: Flask, startup_env_logger: logging.Logger) -> None:
    with app.app_context():
        run_startup_env_checks(app, startup_env_logger)


def _register_flash_logging(app: Flask, flash_logger: logging.Logger) -> None:
    def _log_flash_message(sender, message, category, **extra):  # pragma: no cover - wiring
        level = logging.INFO
        normalized = (category or "").lower()
        if normalized in {"error", "danger"}:
            level = logging.ERROR
        elif normalized in {"warning", "warn"}:
            level = logging.WARNING
        flash_logger.log(level, "Flash[%s]: %s", category or "message", message)

    message_flashed.connect(_log_flash_message, app)


def _register_acl_context(app: Flask) -> None:
    @app.context_processor
    def inject_acl():
        from flask_login import current_user as cu
        from utils.notifications import get_unread_notifications_count_cached
        def current_user_has(*roles):
            try:
                return cu.is_authenticated and cu.has_role(*roles)
            except Exception:
                return False
        unread_count = 0
        if cu.is_authenticated:
            try:
                user_id = cu.id
            except Exception:
                try:
                    user_id = int(cu.get_id()) if cu.get_id() else None
                except Exception:
                    user_id = None
            if user_id is not None:
                unread_count = get_unread_notifications_count_cached(user_id)
        return dict(current_user_has=current_user_has, unread_notification_count=unread_count)


def _register_request_timing(app: Flask, http_error_logger: logging.Logger) -> None:
    @app.before_request
    def start_timer():
        request.start_time = time.time()

    @app.after_request
    def log_response(response):
        duration_ms = None
        if hasattr(request, "start_time"):
            duration_ms = int((time.time() - request.start_time) * 1000)

        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        client_ip = forwarded_for or request.remote_addr or "-"
        ua = request.headers.get("User-Agent", "-")
        full_url = request.url

        if request.path == "/login" and response.status_code == 200:
            if hasattr(response, 'headers'):
                set_cookie_headers = {k: v for k, v in response.headers.items() if k.lower() == 'set-cookie'}
                auth_logger = logging.getLogger("auth")
                if set_cookie_headers:
                    auth_logger.info(
                        "Login response - Setting cookies: %s",
                        sanitize_log_value(set_cookie_headers),
                    )
                else:
                    auth_logger.info("Login response - No cookies being set")

        line = (
            f"{sanitize_log_value(client_ip)} {sanitize_log_value(request.method)} "
            f"{sanitize_log_value(full_url)} {sanitize_log_value(response.status_code)} "
            f"UA={sanitize_log_value(ua)} duration={sanitize_log_value(duration_ms if duration_ms is not None else '-')}ms"
        )

        if response.status_code >= 400:
            http_error_logger.warning(line)

        try:
            if hasattr(response, 'headers') and not response.headers.get('X-RateLimit-Limit'):
                from flask import g
                if hasattr(g, 'limiter_limit') and hasattr(g, 'limiter_remaining'):
                    response.headers['X-RateLimit-Limit'] = str(g.limiter_limit)
                    response.headers['X-RateLimit-Remaining'] = str(g.limiter_remaining)
                    if hasattr(g, 'limiter_reset'):
                        response.headers['X-RateLimit-Reset'] = str(g.limiter_reset)
        except Exception as e:
            rate_limit_logger = logging.getLogger("rate_limit")
            rate_limit_logger.warning(
                "Failed to add rate limit headers: %s",
                sanitize_log_value(e),
            )

        return response


def _register_response_headers(app: Flask) -> None:
    @app.after_request
    def prevent_duplicate_headers(response):
        if 'Date' in response.headers:
            del response.headers['Date']
        if 'Server' in response.headers:
            del response.headers['Server']
        return response

    @app.after_request
    def add_rate_limit_headers(response):
        try:
            from flask import g

            if hasattr(g, '_rate_limit_limit'):
                response.headers['X-RateLimit-Limit'] = str(g._rate_limit_limit)
            if hasattr(g, '_rate_limit_remaining'):
                response.headers['X-RateLimit-Remaining'] = str(g._rate_limit_remaining)
            if hasattr(g, '_rate_limit_reset'):
                response.headers['X-RateLimit-Reset'] = str(g._rate_limit_reset)

            if not response.headers.get('X-RateLimit-Limit'):
                try:
                    from utils.rate_limiter import limiter
                    key = limiter.key_func()
                    if key:
                        storage = limiter.storage
                        if storage:
                            window = storage.get_window(key)
                            if window:
                                response.headers['X-RateLimit-Limit'] = str(window.limit)
                                response.headers['X-RateLimit-Remaining'] = str(window.remaining)
                                response.headers['X-RateLimit-Reset'] = str(window.reset_time)
                except Exception:
                    pass

        except Exception as e:
            rate_limit_logger = logging.getLogger("rate_limit")
            rate_limit_logger.warning(
                "Failed to add rate limit headers: %s",
                sanitize_log_value(e),
            )

        return response


def _register_inactivity_timeout(app: Flask) -> None:
    @app.before_request
    def _enforce_inactivity_timeout():
        from flask_login import current_user, logout_user
        p = request.path or "/"
        if p.startswith("/static/") or p == "/login":
            return
        if not current_user.is_authenticated:
            return
        try:
            last = int(session.get("last_active", 0))
        except Exception:
            last = 0
        import time as _t
        now = int(_t.time())
        timeout_s = app.config.get("INACTIVITY_TIMEOUT_MINUTES", 30) * 60
        if last and (now - last) > timeout_s:
            from auth.utils import get_client_ip
            username = getattr(current_user, 'username', 'Unknown') if current_user.is_authenticated else 'Unknown'
            ip = get_client_ip()
            auth_logger = logging.getLogger("auth")
            auth_logger.info(
                "Session timeout - User: %s, IP: %s, Last active: %s, Timeout duration: %s minutes",
                sanitize_log_value(username),
                sanitize_log_value(ip),
                sanitize_log_value(last),
                sanitize_log_value(timeout_s // 60),
            )

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


def _register_blueprints(app: Flask) -> None:
    from jobs import jobs_bp
    from uploaded_zips import bp as uploaded_zips_bp
    from screenings import bp as screenings_bp
    from reports import bp as reports_bp
    from analytics import bp as analytics_bp
    from search import bp as search_bp
    from verify_remedio import bp as verify_remedio_bp
    from verify_remedio_glaucoma import bp as verify_remedio_glaucoma_bp
    from verify_remedio_dr import bp as verify_remedio_dr_bp
    from verify_remedio_nodr import bp as verify_remedio_nodr_bp
    from media import bp as media_bp
    from account import account_bp
    from audit import bp as audit_bp
    from grading import bp as grading_bp
    from direct_uploads import bp as direct_uploads_bp
    from remedio_zip_uploads import bp as remedio_zip_uploads_bp
    from preprocess import bp as preprocess_bp
    from notifications import bp as notifications_bp
    from tasks import bp as tasks_bp
    from tasks.ad_hoc import bp as ad_hoc_tasks_bp
    from help import bp as help_bp
    from review import bp as review_bp
    from public import bp as public_bp
    from admin import admin_bp
    from admin.rate_limit_admin import rate_limit_admin_bp
    from dashboard import dashboard_bp
    from api import api_bp
    from docs import docs_bp
    from datasets import bp as datasets_bp

    app.register_blueprint(jobs_bp)
    app.register_blueprint(uploaded_zips_bp)
    app.register_blueprint(screenings_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(verify_remedio_bp)
    app.register_blueprint(verify_remedio_glaucoma_bp)
    app.register_blueprint(verify_remedio_dr_bp)
    app.register_blueprint(verify_remedio_nodr_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(grading_bp)
    app.register_blueprint(direct_uploads_bp)
    app.register_blueprint(remedio_zip_uploads_bp)
    app.register_blueprint(preprocess_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(ad_hoc_tasks_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(rate_limit_admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(datasets_bp)


def _register_auth(app: Flask) -> None:
    from auth.routes import auth_bp, login_manager
    app.register_blueprint(auth_bp)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"


def _register_login_guard(app: Flask) -> None:
    @app.before_request
    def _require_login_everywhere():
        from flask_login import current_user, logout_user
        path = request.path or "/"

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
            or path == "/robots.txt"
            or path == "/style_guide"
            or path == "/forgot-password"
            or path == "/reset-password"
            or path == "/healthz"
            or path == "/check-email-status"
            or path == "/email-sse"
            or path == "/test-rate-limit"
            or path == "/refresh-captcha"
            or path == "/captcha-audio"
            or path.startswith("/help")
            or path == "/analytics"
            or path == "/sitemap.xml"
            or path.startswith("/api/analytics/")
            or path.startswith("/datasets/download")
        ):
            return
        if not current_user.is_authenticated:
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


def _register_stack_trace_handlers(app: Flask) -> None:
    @app.before_request
    def _global_stack_trace_handler():
        import time as _t
        request._start_time = _t.time()
        runtime_logger = logging.getLogger("runtime_error")
        if runtime_logger.isEnabledFor(logging.DEBUG):
            from utils.stack_trace_handler import log_current_stack
            log_current_stack(f"Processing request: {request.method} {request.url}")

    @app.after_request
    def _global_stack_trace_after_handler(response):
        import time as _t
        runtime_logger = logging.getLogger("runtime_error")
        duration = None
        if hasattr(request, '_start_time'):
            duration = _t.time() - request._start_time
        if runtime_logger.isEnabledFor(logging.DEBUG):
            runtime_logger.debug(
                "Request completed: %s %s Status: %s Duration: %.3fs",
                sanitize_log_value(request.method),
                sanitize_log_value(request.url),
                sanitize_log_value(response.status_code),
                duration or 0.0,
            )
        return response

    @app.errorhandler(Exception)
    def _global_exception_handler(e):
        from utils.stack_trace_handler import log_stack_trace
        log_stack_trace(
            message=f"Global exception handler caught: {type(e).__name__}",
            exception=e,
        )
        current_app.logger.exception("Unhandled exception in request: %s", e)
        return render_template("errors/500.html"), 500


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        auth_logger = logging.getLogger("auth")
        auth_logger.error(
            "CSRF Error - Message: %s",
            sanitize_log_value(e.description or "Unknown CSRF error"),
        )
        auth_logger.error(
            "CSRF Error - Request: %s %s",
            sanitize_log_value(request.method),
            sanitize_log_value(request.url),
        )
        auth_logger.error(
            "CSRF Error - User-Agent: %s",
            sanitize_log_value(request.headers.get("User-Agent", "Unknown")),
        )
        auth_logger.error(
            "CSRF Error - Referer: %s",
            sanitize_log_value(request.headers.get("Referer", "None")),
        )
        auth_logger.error(
            "CSRF Error - Form data keys: %s",
            sanitize_log_value(list(request.form.keys()) if request.form else "None"),
        )
        auth_logger.error(
            "CSRF Error - Headers: %s",
            sanitize_log_headers(dict(request.headers)),
        )

        flash(e.description or "Security check failed. Please try again.", "danger")
        target = request.referrer or url_for("homepage")
        if not is_safe_url(target):
            target = url_for("homepage")
        return redirect(target), 400

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
        from utils.stack_trace_handler import log_stack_trace
        log_stack_trace(
            message="500 Internal Server Error",
            exception=e,
        )
        return render_template("errors/500.html"), 500

    @app.errorhandler(Exception)
    def handle_generic_exception(e):
        from utils.stack_trace_handler import log_stack_trace
        log_stack_trace(
            message=f"Unhandled exception: {type(e).__name__}",
            exception=e,
        )
        current_app.logger.exception("Unhandled exception: %s", e)
        return render_template("errors/500.html"), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        return (
            render_template(
                "errors/error.html",
                code=getattr(e, "code", 500),
                title=getattr(e, "name", "Error"),
                message=getattr(e, "description", "An unexpected error occurred."),
            ),
            getattr(e, "code", 500),
        )


def _register_utility_routes(app: Flask) -> None:
    @app.get('/favicon.ico')
    @rate_limit("100 per minute")
    def _favicon():
        return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

    @app.get('/robots.txt')
    @rate_limit("100 per minute")
    def _robots():
        return send_from_directory(app.static_folder, 'robots.txt', mimetype='text/plain')

    @app.get("/sitemap.xml")
    @rate_limit("100 per minute")
    def sitemap():
        base_url = (current_app.config.get("BASE_URL") or "").rstrip("/")
        if not base_url:
            base_url = request.url_root.rstrip("/")

        urls = [
            (f"{base_url}/", "daily", "1.0"),
            (f"{base_url}/help", "weekly", "0.4"),
            (f"{base_url}/help/", "weekly", "0.4"),
            (f"{base_url}/analytics", "weekly", "0.3"),
            (f"{base_url}/style_guide", "monthly", "0.2"),
            (f"{base_url}/robots.txt", "yearly", "0.1"),
        ]

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for loc, changefreq, priority in urls:
            xml_lines.append("  <url>")
            xml_lines.append(f"    <loc>{loc}</loc>")
            xml_lines.append(f"    <changefreq>{changefreq}</changefreq>")
            xml_lines.append(f"    <priority>{priority}</priority>")
            xml_lines.append("  </url>")
        xml_lines.append("</urlset>")

        response = current_app.response_class(
            "\n".join(xml_lines),
            mimetype="application/xml",
        )
        return response

    @app.route("/")
    @rate_limit("60 per minute")
    def homepage():
        from home import homepage as home_page
        return home_page()

    @app.route("/home", endpoint="home.index")
    @rate_limit("60 per minute")
    def home_index_alias():
        from home import homepage as home_page
        return home_page()

    @app.route("/style_guide")
    @rate_limit("30 per minute")
    def style_guide():
        return render_template("style_guide.html")

    @app.route("/test-rate-limit")
    @rate_limit("10 per minute")
    def test_rate_limit():
        return jsonify({"message": "Rate limit test endpoint", "timestamp": time.time()})

    @app.route("/healthz", methods=["GET"])
    @rate_limit("100 per minute")
    def healthz():
        db = Session()
        try:
            db.query(Job.id).limit(1).first()
            return jsonify({
                "status": "ok"
                }
            )
        except Exception as e:
            current_app.logger.error("Health check failed: %s", sanitize_log_value(e))
            return jsonify({"status": "error", "message": "Database connection failed"}), 500
        finally:
            db.close()


def _initialize_schedulers(
    app: Flask,
    materialized_view_logger: logging.Logger,
    thumbnail_maintenance_logger: logging.Logger,
) -> None:
    if app.config.get("MATERIALIZED_VIEW_SCHEDULE_ENABLED", False):
        try:
            from utils.materialized_view_scheduler import initialize_scheduler
            scheduler_thread = initialize_scheduler(app)
            if scheduler_thread:
                scheduler_thread.start()
                materialized_view_logger.info("Materialized view scheduler started successfully")
            else:
                materialized_view_logger.info("Materialized view scheduler disabled")
        except Exception as e:
            materialized_view_logger.error(
                "Failed to start materialized view scheduler: %s",
                sanitize_log_value(e),
            )
    else:
        materialized_view_logger.info("Materialized view scheduler disabled by configuration")

    if app.config.get("THUMBNAIL_MAINTENANCE_ENABLED", False):
        try:
            from utils.thumbnail_maintenance_scheduler import initialize_scheduler
            maintenance_scheduler_thread = initialize_scheduler(app)
            if maintenance_scheduler_thread:
                maintenance_scheduler_thread.start()
                thumbnail_maintenance_logger.info("Thumbnail maintenance scheduler started successfully")
            else:
                thumbnail_maintenance_logger.info("Thumbnail maintenance scheduler disabled")
        except Exception as e:
            thumbnail_maintenance_logger.error(
                "Failed to start thumbnail maintenance scheduler: %s",
                sanitize_log_value(e),
            )
    else:
        thumbnail_maintenance_logger.info("Thumbnail maintenance scheduler disabled by configuration")


def _initialize_email_config(app: Flask) -> None:
    try:
        from utils.email_config import EmailConfigService
        with app.app_context():
            EmailConfigService.update_flask_config()
        app.logger.info("Email configuration initialized from database or environment")
    except Exception as e:
        app.logger.warning(
            "Failed to initialize email configuration: %s",
            sanitize_log_value(e),
        )


def create_app():
    load_environment()

    app = Flask(
        __name__,
        static_folder="static",
        static_url_path="/static",
    )

    _configure_base_settings(app)
    _register_template_filters(app)
    _register_default_theme_context(app)
    force_https = _configure_session_and_proxy(app)
    _configure_executors(app)
    _register_csrf_protection(app)
    cache.init_app(app)
    app.session_interface = DatabaseSessionInterface()
    if force_https:
        _register_https_redirect(app)

    _initialize_middleware(app)
    setup_environment()
    _ensure_core_roles()

    loggers = _configure_logging_services(app)
    _run_startup_checks(app, loggers["startup_env"])
    _register_flash_logging(app, loggers["flash"])
    _register_acl_context(app)
    register_csp(app)
    _register_request_timing(app, loggers["http_error"])
    _register_inactivity_timeout(app)
    _register_response_headers(app)

    _register_blueprints(app)
    _register_auth(app)
    _register_login_guard(app)
    _register_stack_trace_handlers(app)
    _register_error_handlers(app)
    _register_utility_routes(app)

    _initialize_schedulers(app, loggers["materialized_view"], loggers["thumbnail_maintenance"])
    _initialize_email_config(app)

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
            logging.error(
                "Error in stuck task cleanup thread: %s",
                sanitize_log_value(e),
            )
            # Even if an error occurs, keep the thread running by sleeping a bit before continuing
            time.sleep(5 * 60)  # Wait 5 minutes before retrying

if __name__ == "__main__":
    app = create_app()
    
    # Start the stuck task cleanup thread
    import threading
    cleanup_thread = threading.Thread(target=run_stuck_task_cleanup, daemon=True)
    cleanup_thread.start()
    
    # dev server; for prod use gunicorn/uwsgi
    flask_port = int(os.getenv("FLASK_PORT", 5001))
    # Use debug mode from environment configuration, default to False
    debug_mode = str(os.getenv("DEBUG", "false")).lower() in ("1", "true", "yes")
    app.run(debug=debug_mode, host="0.0.0.0", port=flask_port)
