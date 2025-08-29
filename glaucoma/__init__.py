from flask import Blueprint

bp = Blueprint("glaucoma", __name__, url_prefix="/glaucoma")

from . import routes  # noqa

