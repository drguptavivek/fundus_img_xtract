from flask import Blueprint

bp = Blueprint("verify_remedio_dr", __name__, url_prefix="/verify_remedio_dr")

from . import routes  # noqa