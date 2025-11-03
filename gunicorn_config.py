"""
Gunicorn configuration file for the Fundus Image Manager application.

This file contains all the Gunicorn settings for running the application
in production. Use this configuration with: gunicorn -c gunicorn_config.py wsgi:application
"""

import os
import multiprocessing
from dotenv import load_dotenv

# Load environment variables from .env file
# This ensures all application configuration is loaded before Gunicorn starts
load_dotenv()

# Server socket
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:5001")
backlog = 2048

# Worker processes
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
preload_app = True
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))
keepalive = 2

# Logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "logs/gunicorn_access.log")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "logs/gunicorn_error.log")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'fundus_img_xtract'

# Server mechanics
daemon = False
pidfile = os.getenv("GUNICORN_PID_FILE", "logs/gunicorn.pid")
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None

# Worker process settings
max_requests = 1000
max_requests_jitter = 50
preload_app = True
worker_tmp_dir = None

# Graceful shutdown timeout
graceful_timeout = 30

# Keep alive timeout
keepalive = 2

# Limit request line and header field sizes
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Hooks
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

# Environment variables
raw_env = [
    f'FLASK_ENV={os.getenv("FLASK_ENV", "production")}',
    f'FLASK_SECRET_KEY={os.getenv("FLASK_SECRET_KEY", "change-me-in-production")}',
]