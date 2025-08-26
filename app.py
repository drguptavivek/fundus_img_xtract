# app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request
from models import Base, engine
from main import setup_environment
from dotenv import load_dotenv  
import time


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


    # Thread pool (shared via app.config)
    app.config["EXECUTOR"] = ThreadPoolExecutor(max_workers=app.config["WORKERS"])

    # Ensure folders + schema (idempotent)
    setup_environment()
    Base.metadata.create_all(engine)

    # ---------------- HTTP loggers ----------------
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    success_log_path = os.getenv("HTTP_SUCCESS_LOG", os.path.join(log_dir, "http_success.log"))
    error_log_path = os.getenv("HTTP_ERROR_LOG", os.path.join(log_dir, "http_error.log"))

    http_success_logger = logging.getLogger("http_success")
    http_error_logger = logging.getLogger("http_error")
    http_success_logger.setLevel(logging.INFO)
    http_error_logger.setLevel(logging.WARNING)

    success_handler = RotatingFileHandler(success_log_path, maxBytes=2 * 1024 * 1024, backupCount=5)
    error_handler = RotatingFileHandler(error_log_path, maxBytes=2 * 1024 * 1024, backupCount=5)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    success_handler.setFormatter(fmt)
    error_handler.setFormatter(fmt)

    http_success_logger.addHandler(success_handler)
    http_error_logger.addHandler(error_handler)

    app.logger.handlers = []  # prevent double logging

    @app.before_request
    def start_timer():
        request.start_time = time.time()

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
    
    from jobs import bp as jobs_bp
    app.register_blueprint(jobs_bp)
    
    from uploaded_results import bp as uploaded_results_bp
    app.register_blueprint(uploaded_results_bp)

    from screenings import bp as screenings_bp
    app.register_blueprint(screenings_bp)

    from reports import bp as reports_bp
    app.register_blueprint(reports_bp)

    from media import bp as media_bp
    app.register_blueprint(media_bp)
    
    # -------------------------------
    # New homepage route
    # -------------------------------
    @app.route("/")
    def homepage():
        return render_template("home.html")
    # -------------------------------

    return app

if __name__ == "__main__":
    app = create_app()
    # dev server; for prod use gunicorn/uwsgi
    app.run(debug=True, host="127.0.0.1", port=5000)
