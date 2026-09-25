"""Dataset blueprint.

Route registration is performed by the Flask application factory so importing
worker-safe dataset services does not pull Flask-only route dependencies into
Celery workers.
"""

from flask import Blueprint

bp = Blueprint("datasets", __name__, url_prefix="/datasets")

__all__ = ["bp"]
