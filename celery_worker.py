"""
Celery worker entrypoint.

This module must not import Flask app or blueprints.
"""

import logging
from celery.signals import worker_process_init
from utils.env_loader import load_environment
from celery_app import celery_app


@worker_process_init.connect
def setup_worker_logging(*args, **kwargs) -> None:
    """
    Initialize application-specific logging for the worker process.
    
    This is called when a worker child process starts. We use a minimal
    Flask-like object to satisfy the configure_logging requirement.
    """
    from app_init.logging_config import configure_logging
    
    class MockApp:
        def __init__(self):
            self.config = {
                "LOG_DIR": None,
                "ENABLE_DEBUG_LOGGING": False,
                "LOG_MAX_BYTES": 2 * 1024 * 1024,
                "LOG_BACKUP_COUNT": 5
            }
            self.debug = False
            self.logger = logging.getLogger("app")

    mock_app = MockApp()
    configure_logging(mock_app)
    
    from app_cache import init_cache
    init_cache()
    
    logging.getLogger("app").info("Worker process logging and cache initialized.")


def main() -> None:
    load_environment()
    celery_app.start()


if __name__ == "__main__":
    main()
