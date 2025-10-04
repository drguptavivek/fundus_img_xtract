"""Tasks blueprint initialization."""

from flask import Blueprint

bp = Blueprint("tasks", __name__, url_prefix="/tasks")

from . import route_index  # noqa: E402,F401
from . import route_my_tasks  # noqa: E402,F401
from . import route_pending  # noqa: E402,F401