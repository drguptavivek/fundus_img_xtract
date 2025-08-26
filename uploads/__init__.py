# uploads/__init__.py
from flask import Blueprint
bp = Blueprint("uploads", __name__, url_prefix="")
from . import routes  # noqa
