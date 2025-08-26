# app.py
import os
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
from models import Base, engine
from main import setup_environment
from dotenv import load_dotenv  


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", 500 * 1024 * 1024))
    app.config["PER_FILE_MAX_BYTES"] = int(os.getenv("PER_FILE_MAX_BYTES", 10 * 1024 * 1024))
    app.config["MAX_FILES_PER_UPLOAD"] = int(os.getenv("MAX_FILES_PER_UPLOAD", 50))
    app.config["WORKERS"] = int(os.getenv("WORKERS", "4"))


    # Thread pool (shared via app.config)
    app.config["EXECUTOR"] = ThreadPoolExecutor(max_workers=app.config["WORKERS"])

    # Ensure folders + schema (idempotent)
    setup_environment()
    Base.metadata.create_all(engine)

    # ✅ relative imports
    from uploads import bp as uploads_bp
    from jobs import bp as jobs_bp

    
    app.register_blueprint(uploads_bp)
    app.register_blueprint(jobs_bp)
    
    return app

if __name__ == "__main__":
    app = create_app()
    # dev server; for prod use gunicorn/uwsgi
    app.run(debug=True, host="127.0.0.1", port=5000)
