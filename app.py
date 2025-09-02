# app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, current_app, jsonify, render_template, request, redirect, url_for, session, flash
from flask import send_from_directory
from models import Base, Job, Session, engine
from main import setup_environment
from dotenv import load_dotenv  
import time
from datetime import timedelta

from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException


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

    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
    app.config["PER_FILE_MAX_BYTES"] = int(os.getenv("PER_FILE_MAX_BYTES", 10 * 1024 * 1024))
    app.config["MAX_FILES_PER_UPLOAD"] = int(os.getenv("MAX_FILES_PER_UPLOAD", 50))
    app.config["WORKERS"] = int(os.getenv("WORKERS", "4"))
    app.config["UPLOADED_RESULTS_PAGE_SIZE"] = int(os.getenv("UPLOADED_RESULTS_PAGE_SIZE", 50))
    app.config["SCREENINGS_PAGE_SIZE"] = int(os.getenv("SCREENINGS_PAGE_SIZE", 50))

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

    # Ensure folders + schema (idempotent)
    setup_environment()
    Base.metadata.create_all(engine)

    # --- RBAC: seed core roles once ---
    from sqlalchemy.orm import sessionmaker
    from auth.roles import ensure_roles, DEFAULT_ROLES
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as db:
        ensure_roles(db, DEFAULT_ROLES)

    # ---------------- HTTP loggers ----------------
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "logs"))
    os.makedirs(log_dir, exist_ok=True)

    success_log_path = os.getenv("HTTP_SUCCESS_LOG", os.path.join(log_dir, "http_success.log"))
    error_log_path   = os.getenv("HTTP_ERROR_LOG",   os.path.join(log_dir, "http_error.log"))

    # Only attach handlers in the reloader child (or when not using the reloader)
    is_reloader_child = (not app.debug) or (os.environ.get("WERKZEUG_RUN_MAIN") == "true")

    http_success_logger = logging.getLogger("http_success")
    http_error_logger   = logging.getLogger("http_error")
    http_success_logger.setLevel(logging.INFO)
    http_error_logger.setLevel(logging.WARNING)
    http_success_logger.propagate = False
    http_error_logger.propagate   = False

    if is_reloader_child:
        # Clean up any old handlers (debug reloader / multiple inits)
        for lg in (http_success_logger, http_error_logger):
            for h in list(lg.handlers):
                lg.removeHandler(h)
                try: h.close()
                except Exception: pass

        disable_rotation = False
        dr_env = os.getenv("HTTP_LOG_DISABLE_ROTATION")
        if dr_env is not None:
            disable_rotation = str(dr_env).lower() in ("1","true","yes")
        elif os.name == "nt":
            disable_rotation = str(os.getenv("ENABLE_LOG_ROTATION_ON_WINDOWS","0")).lower() not in ("1","true","yes")

        if disable_rotation:
            from logging import FileHandler
            success_handler = FileHandler(success_log_path, encoding="utf-8", delay=True)
            error_handler   = FileHandler(error_log_path,   encoding="utf-8", delay=True)
        else:
            success_handler = RotatingFileHandler(success_log_path, maxBytes=2*1024*1024,
                                                  backupCount=5, encoding="utf-8", delay=True)
            error_handler   = RotatingFileHandler(error_log_path,   maxBytes=2*1024*1024,
                                                  backupCount=5, encoding="utf-8", delay=True)

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        success_handler.setFormatter(fmt)
        error_handler.setFormatter(fmt)

        http_success_logger.addHandler(success_handler)
        http_error_logger.addHandler(error_handler)

        # Keep app.logger free of its own handlers; route its warnings/errors to error file
        app.logger.handlers = []
        app.logger.setLevel(logging.INFO)
        app.logger.addHandler(error_handler)

        # Also send Werkzeug access lines to success file (nice to have)
        wz = logging.getLogger("werkzeug")
        wz.setLevel(logging.INFO)
        wz.propagate = False
        wz.handlers = [success_handler]

        # Emit a one-time startup line so you can verify file opens
        http_success_logger.info("HTTP success logger initialized at %s", success_log_path)

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
            logout_user()
            session.clear()
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
            f"{client_ip} \"{request.method} {full_url}\" "
            f"{response.status_code} "
            f"UA=\"{ua}\" "
            f"duration={duration_ms if duration_ms is not None else '-'}ms"
        )

        if response.status_code < 400:
            http_success_logger.info(line)
        else:
            http_error_logger.warning(line)

        return response

    #  relative imports
    from uploads import bp as uploads_bp
    app.register_blueprint(uploads_bp)
    
    from jobs import jobs_bp
    app.register_blueprint(jobs_bp)
    
    from uploaded_results import bp as uploaded_results_bp
    app.register_blueprint(uploaded_results_bp)

    from screenings import bp as screenings_bp
    app.register_blueprint(screenings_bp)

    from reports import bp as reports_bp
    app.register_blueprint(reports_bp)

    from glaucoma import bp as glaucoma_bp
    app.register_blueprint(glaucoma_bp)

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

    from preprocess import bp as preprocess_bp
    app.register_blueprint(preprocess_bp)

        # -------- Auth blueprint + Flask-Login --------
    # (Requires the auth/ package provided earlier)
    from auth.routes import auth_bp, login_manager
    app.register_blueprint(auth_bp)            # /login, /logout
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Global guard: require login for everything except login page, static, favicon
    @app.before_request
    def _require_login_everywhere():
        from flask_login import current_user
        path = request.path or "/"
        if (
            path == "/" 
            or path == "/login"
            or path.startswith("/static/")
            or path == "/favicon.ico"
            or path == "/style_guide"
        ):
            return  # allowed without auth
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

    from admin import admin_bp
    app.register_blueprint(admin_bp)



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

    # Serve classic /favicon.ico path for browsers that request it directly
    @app.get('/favicon.ico')
    def _favicon():
        return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

    # -------------------------------
    # New homepage route
    @app.route("/")
    def homepage():
        # Compute counts for the public home (unauthenticated visitors)
        from sqlalchemy import select, func, or_
        from models import Session, EncounterFile, PatientEncounters
        img_exts = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]  # same set the app serves
        with Session() as db:
            img_filters = [func.lower(EncounterFile.filename).like(f"%{ext}") for ext in img_exts]
            images_count = db.execute(
                select(func.count(EncounterFile.id)).where(or_(*img_filters))
            ).scalar_one()
            screenings_count = db.execute(
                select(func.count(PatientEncounters.id))
            ).scalar_one()

        return render_template(
            "home.html",
            images_count=images_count,
            screenings_count=screenings_count,
        )
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

if __name__ == "__main__":
    app = create_app()
    # dev server; for prod use gunicorn/uwsgi
    app.run(debug=True, host="127.0.0.1", port=5000)
