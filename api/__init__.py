# api/__init__.py
from flask import Blueprint

# Create the API blueprint with /api prefix
api_bp = Blueprint("fundus_api", __name__, url_prefix="/api")

# Import all route handlers
from . import routes
