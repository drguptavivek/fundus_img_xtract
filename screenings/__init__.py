# screenings/__init__.py
from flask import Blueprint
bp = Blueprint("screenings", __name__, url_prefix="/screenings")
from . import routes  # noqa
