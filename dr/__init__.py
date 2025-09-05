from flask import Blueprint

bp = Blueprint("dr", __name__, url_prefix="/dr")

from . import routes  # noqa