# jobs/__init__.py
from flask import Blueprint
bp = Blueprint("jobs", __name__, url_prefix="")
from . import routes  # noqa
