"""Gunicorn configuration for the Fundus Image Manager application."""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

from utils.env_loader import load_environment


def _int_from_env(var_name: str, default: int, *, minimum: int | None = None) -> int:
    """Parse integer env vars safely, falling back to a default."""

    value = os.getenv(var_name)
    if value is None:
        return default if minimum is None else max(default, minimum)
    try:
        result = int(value)
    except ValueError:
        return default if minimum is None else max(default, minimum)
    if minimum is not None:
        return max(result, minimum)
    return result


load_environment()

# Server socket
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:5001")
backlog = _int_from_env("GUNICORN_BACKLOG", 2048, minimum=1024)

# Worker processes
default_workers = multiprocessing.cpu_count() * 2 + 1
workers = _int_from_env("GUNICORN_WORKERS", default_workers, minimum=2)
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
max_requests = _int_from_env("GUNICORN_MAX_REQUESTS", 1000, minimum=100)
max_requests_jitter = _int_from_env("GUNICORN_MAX_REQUESTS_JITTER", 100, minimum=0)
preload_app = os.getenv("GUNICORN_PRELOAD", "true").lower() in {"1", "true", "yes"}
timeout = _int_from_env("GUNICORN_TIMEOUT", 120, minimum=30)
keepalive = _int_from_env("GUNICORN_KEEPALIVE", 2, minimum=1)

# Logging
log_dir = Path(os.getenv("GUNICORN_LOG_DIR", "/var/log/fundus-img-xtract"))
accesslog = os.getenv("GUNICORN_ACCESS_LOG", str(log_dir / "gunicorn_access.log"))
errorlog = os.getenv("GUNICORN_ERROR_LOG", str(log_dir / "gunicorn_error.log"))
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "fundus_img_xtract"

# Server mechanics
daemon = False
pidfile = os.getenv("GUNICORN_PID_FILE", str(Path(os.getenv("RUNTIME_DIR", "/var/run/fundus-img-xtract")) / "gunicorn.pid"))
user = os.getenv("GUNICORN_USER")
group = os.getenv("GUNICORN_GROUP")
tmp_upload_dir = os.getenv("GUNICORN_TMP_UPLOAD_DIR")

# SSL (if needed)
keyfile = os.getenv("GUNICORN_SSL_KEYFILE")
certfile = os.getenv("GUNICORN_SSL_CERTFILE")

worker_tmp_dir = os.getenv("GUNICORN_WORKER_TMP_DIR")

# Graceful shutdown timeout
graceful_timeout = _int_from_env("GUNICORN_GRACEFUL_TIMEOUT", 30, minimum=10)

# Limit request line and header field sizes
limit_request_line = _int_from_env("GUNICORN_LIMIT_REQUEST_LINE", 4094, minimum=1024)
limit_request_fields = _int_from_env("GUNICORN_LIMIT_REQUEST_FIELDS", 100, minimum=10)
limit_request_field_size = _int_from_env("GUNICORN_LIMIT_REQUEST_FIELD_SIZE", 8190, minimum=1024)


def on_starting(server):
    """
    Called just before the master process is initialized.
    """
    server.log.info("Server is starting...")

def on_reload(server):
    """
    Called to recycle workers during a reload via SIGHUP.
    """
    server.log.info("Server is reloading...")

def when_ready(server):
    """
    Called just after the server is started.
    """
    server.log.info("Server is ready.")

def worker_int(worker):
    """
    Called just after a worker exited on SIGINT or SIGQUIT.
    """
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """
    Called just before a worker is forked.
    """
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """
    Called just after a worker has been forked.
    """
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    """
    Called just after a worker has initialized the application.
    """
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

def worker_abort(worker):
    """
    Called when a worker received the SIGABRT signal.
    """
    worker.log.info("Worker aborted (pid: %s)", worker.pid)
