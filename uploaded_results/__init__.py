# uploaded_results/__init__.py
from flask import Blueprint
bp = Blueprint("uploaded_results", __name__, url_prefix="")
from . import routes  # noqa
