from flask import Blueprint

bp = Blueprint("verify_remedio_nodr", __name__, url_prefix="/verify_remedio_nodr")

from . import routes  # noqa: E402,F401
