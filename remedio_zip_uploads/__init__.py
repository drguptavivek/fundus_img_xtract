# remedio_zip_uploads/__init__.py
from flask import Blueprint
from auth.roles import roles_any, roles_required

bp = Blueprint("remedio_zip_uploads", __name__, url_prefix="/remedio_zip_uploads")
from . import routes  # noqa
