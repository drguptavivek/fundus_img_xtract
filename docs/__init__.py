# docs/__init__.py
from flask import Blueprint

docs_bp = Blueprint("docs", __name__, url_prefix="/docs")

from . import routes, swagger_ui