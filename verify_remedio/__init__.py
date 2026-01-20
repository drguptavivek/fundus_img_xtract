from flask import Blueprint

bp = Blueprint("verify_remedio", __name__, url_prefix="/verify_remedio")

from . import routes  # noqa: E402,F401
