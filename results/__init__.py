"""Results blueprint initialization."""

from flask import Blueprint

bp = Blueprint("results", __name__, url_prefix="/results")

from . import routes  # noqa: E402,F401
