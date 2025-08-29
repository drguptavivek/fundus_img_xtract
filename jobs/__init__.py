# jobs/__init__.py
from flask import Blueprint

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs" )

from . import routes 
