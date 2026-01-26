"""Shared Flask-Caching instance for the application."""

from __future__ import annotations

import logging
import os
from flask_caching import Cache

logger = logging.getLogger(__name__)

# Initialized in app.create_app via cache.init_app(app)
cache: Cache = Cache()


def init_cache(app=None) -> None:
    """Initialize the cache instance.

    If app is provided, it uses app.config.
    If app is None (e.g. in Celery workers), it uses environment variables.
    """
    if app is not None:
        logger.info("Initializing cache with provided app")
        cache.init_app(app)
        return

    # Check if cache is already initialized by verifying app attribute exists and is valid
    try:
        if hasattr(cache, 'app') and cache.app is not None and hasattr(cache.app, 'config'):
            logger.debug("Cache already initialized")
            return
    except AttributeError:
        # If checking attributes fails, proceed with initialization
        pass

    # Fallback for non-Flask contexts (like Celery workers)
    logger.info("Initializing cache for non-Flask context")
    from utils.redis_connection import build_redis_url

    config = {
        "CACHE_TYPE": os.getenv("CACHE_TYPE", "RedisCache"),
        "CACHE_REDIS_URL": os.getenv("CACHE_REDIS_URL") or build_redis_url(),
        "CACHE_DEFAULT_TIMEOUT": int(os.getenv("CACHE_DEFAULT_TIMEOUT", 900)),
        "CACHE_KEY_PREFIX": os.getenv("CACHE_KEY_PREFIX", "fim:cache:"),
    }

    # Flask-Caching init_app needs an object with a .config attribute.
    # We provide a minimal mock app object to satisfy this and ensure
    # cache methods don't fail when looking for an app context.
    class MockJinjaEnv:
        """Minimal mock Jinja2 environment to satisfy Flask-Caching."""
        def __init__(self):
            self._template_fragment_cache = {}

        def add_extension(self, extension):
            """Mock method - Flask-Caching calls this to register its extension."""
            pass

    class MockApp:
        def __init__(self, conf):
            self.config = conf
            self.extensions = {}
            self.name = "MockApp"
            self.jinja_env = MockJinjaEnv()  # Flask-Caching needs this for template fragment caching

        def teardown_appcontext(self, f):
            return f

    mock_app = MockApp(config)
    cache.init_app(mock_app)

    # Always force set .app attribute to ensure it's available
    cache.app = mock_app

    logger.info("Cache initialized successfully with MockApp")

    