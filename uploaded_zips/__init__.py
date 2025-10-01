# uploaded_zips/__init__.py
from flask import Blueprint


bp = Blueprint("uploaded_zips", __name__, url_prefix="")

from . import routes  # noqa: E402,F401
