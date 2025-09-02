from flask import Blueprint

bp = Blueprint(
    "preprocess",
    __name__,
    template_folder="templates",
    static_folder="static",
    url_prefix="/preprocess"
)

from . import anonymize_image