from flask import Blueprint

# Credential-authenticated, read-only project mirror API for desktop clients.
project_sync_api_bp = Blueprint("project_sync_api", __name__, url_prefix="/api/sync/v1")

from . import routes  # noqa: E402,F401
