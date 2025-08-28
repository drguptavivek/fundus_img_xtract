# uploaded_results/__init__.py
from flask import Blueprint
from auth.roles import roles_any, roles_required


bp = Blueprint("uploaded_results", __name__, url_prefix="")
from . import routes  # noqa
