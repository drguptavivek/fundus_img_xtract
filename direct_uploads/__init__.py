from flask import Blueprint

bp = Blueprint(
    "direct_uploads",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/direct_uploads",
)

from . import upload, dashboard, jobs, api, edit_upload, edit_image, save_image  # noqa: E402,F401