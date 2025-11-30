"""Shared Flask-Caching instance for the application."""

from __future__ import annotations

from flask_caching import Cache

# Initialized in app.create_app via cache.init_app(app)
cache: Cache = Cache()
