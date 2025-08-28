#reports/__init__.py
from flask import Blueprint
from auth.roles import roles_any, roles_required

bp = Blueprint("reports", __name__, url_prefix="/reports")
from . import routes  # noqa
