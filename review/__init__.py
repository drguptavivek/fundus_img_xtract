from flask import Blueprint

bp = Blueprint(
    'review', 
    __name__, 
    url_prefix='/review')


def register_routes() -> None:
    """Import page routes only while constructing the Flask application.

    Keeping package import free of route side effects lets background workers
    import domain modules such as ``review.discrepancy_export`` without also
    importing authentication pages and the rest of the web-only stack.
    """
    from . import route_discrepancy_review  # noqa: F401
    from . import route_regrade_tasks  # noqa: F401
    from . import task_review  # noqa: F401
