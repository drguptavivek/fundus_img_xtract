# screenings/__init__.py
from flask import Blueprint
from auth.roles import roles_any, roles_required


bp = Blueprint("screenings", __name__, url_prefix="/screenings")
from . import routes  # noqa
