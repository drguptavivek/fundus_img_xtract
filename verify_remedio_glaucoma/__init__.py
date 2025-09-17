from flask import Blueprint

bp = Blueprint("verify_remedio_glaucoma", __name__, url_prefix="/verify_remedio_glaucoma")

from . import routes  # noqa

