from flask import Blueprint

# Create the notifications blueprint
bp = Blueprint("notifications", __name__, url_prefix="/notifications")

# Import all route handlers
from . import notifications

# Register routes with the blueprint
notifications.register_routes(bp)