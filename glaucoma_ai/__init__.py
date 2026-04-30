from flask import Blueprint

bp = Blueprint("glaucoma_ai", __name__, url_prefix="/glaucoma-ai")

from . import routes  # noqa: E402,F401
