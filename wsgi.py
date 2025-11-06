"""WSGI entry point for Gunicorn server."""

from __future__ import annotations

import logging
import os

from app import create_app
from utils.env_loader import load_environment

logger = logging.getLogger(__name__)

# Load configuration files before expanding env references
load_environment()

for key, value in list(os.environ.items()):
    if isinstance(value, str) and "${" in value:
        try:
            os.environ[key] = os.path.expandvars(value)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Unable to expand environment variable %s", key, exc_info=exc)

application = create_app()

if __name__ == "__main__":
    # Allow running via `python wsgi.py` for local troubleshooting only.
    debug_flag = any(
        value.lower() in {"1", "true", "yes"}
        for value in (
            os.getenv("FLASK_DEBUG", "false"),
            os.getenv("DEBUG", "false"),
            os.getenv("ENABLE_DEBUG_LOGGING", "false"),
        )
    )
    host = os.getenv("FLASK_HOST", os.getenv("FLASK_RUN_HOST", "127.0.0.1"))
    try:
        port = int(os.getenv("FLASK_PORT", os.getenv("FLASK_RUN_PORT", "5001")))
    except ValueError:
        port = 5001

    application.run(debug=debug_flag, host=host, port=port)
