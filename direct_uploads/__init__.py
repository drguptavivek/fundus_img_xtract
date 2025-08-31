from flask import Blueprint

bp = Blueprint(
    "direct_uploads",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/direct_uploads",
)

from . import routes
