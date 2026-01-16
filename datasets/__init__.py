"""Dataset share/download routes."""

from flask import Blueprint

bp = Blueprint("datasets", __name__, url_prefix="/datasets")

from . import routes  # noqa: E402,F401

__all__ = ["bp"]
