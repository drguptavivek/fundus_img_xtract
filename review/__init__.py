from flask import Blueprint

bp = Blueprint(
    'review', 
    __name__, 
    url_prefix='/review')

# Import routes to register them with the blueprint
from . import route_discrepancy_review, route_regrade_tasks, task_review
