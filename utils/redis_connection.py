"""Centralized Redis connection utility following the PostgreSQL configuration pattern."""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import quote

from utils.env_loader import get_env

_LOGGER = logging.getLogger(__name__)


def build_redis_url() -> str:
    """Construct a Redis URL from available environment variables.
    
    Priority order for Redis host:
    1. REDIS_HOST_OVERRIDE (highest priority, for temporary overrides)
    2. REDIS_HOST_LOCAL (for local development)
    3. REDIS_HOST (for Docker environments)
    4. Fallback to "127.0.0.1" if none are set
    
    Uses REDIS_PASSWORD from deploy.secrets.env for authentication.
    Defaults to port 6379 and database 0.
    
    Returns:
        Redis connection URL in format: redis://[password@]host:port/0
    """
    # Get Redis host with priority order
    host_override = get_env("REDIS_HOST_OVERRIDE") or get_env("REDIS_HOST_LOCAL")
    redis_host_raw = host_override if host_override and host_override.strip() else get_env("REDIS_HOST")
    redis_host = (redis_host_raw or "127.0.0.1").strip()
    
    # Get Redis password from secrets
    redis_password = get_env("REDIS_PASSWORD")
    
    # Get port with default
    raw_port = get_env("REDIS_PORT")
    redis_port = raw_port.strip() if raw_port else "6379"
    
    # Get database number with default
    raw_db = get_env("REDIS_DB")
    redis_db = raw_db.strip() if raw_db else "0"
    
    # Build Redis URL
    if redis_password and redis_password.strip():
        password_part = f":{quote(redis_password.strip(), safe='')}@"
    else:
        password_part = ""
    
    redis_url = f"redis://{password_part}{redis_host}:{redis_port}/{redis_db}"
    # print(f"redis_url = redis://{password_part}{redis_host}:{redis_port}/{redis_db}")
    _LOGGER.debug(f"Built Redis URL: redis://{'*' * len(password_part) if password_part else ''}{redis_host}:{redis_port}/{redis_db}")
    
    return redis_url


def get_redis_connection_params() -> dict[str, str | int]:
    """Get Redis connection parameters as a dictionary.
    
    This is useful for Redis clients that prefer separate parameters
    rather than a connection URL.
    
    Returns:
        Dictionary with connection parameters: host, port, password, db
    """
    # Get Redis host with priority order
    host_override = get_env("REDIS_HOST_OVERRIDE") or get_env("REDIS_HOST_LOCAL")
    redis_host_raw = host_override if host_override and host_override.strip() else get_env("REDIS_HOST")
    redis_host = (redis_host_raw or "127.0.0.1").strip()
    
    # Get other parameters
    redis_password = get_env("REDIS_PASSWORD")
    raw_port = get_env("REDIS_PORT")
    redis_port = int(raw_port.strip()) if raw_port else 6379
    raw_db = get_env("REDIS_DB")
    redis_db = int(raw_db.strip()) if raw_db else 0
    
    params = {
        "host": redis_host,
        "port": redis_port,
        "db": redis_db,
    }
    
    # Only add password if it exists
    if redis_password and redis_password.strip():
        params["password"] = redis_password.strip()
    
    return params