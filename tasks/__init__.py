from flask import Blueprint

bp = Blueprint("tasks", __name__, url_prefix="/tasks")

# Register routes
from . import route_index  # noqa: F401
from . import route_pending  # noqa: F401
from . import route_task_details  # noqa: F401
from . import route_intra_rater  # noqa: F401
from . import route_organizationalTasks  # noqa: F401
