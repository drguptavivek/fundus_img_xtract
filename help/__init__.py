from flask import Blueprint

bp = Blueprint(
    "help",
    __name__,
    template_folder="templates",
    url_prefix="/help",
)



from . import routes