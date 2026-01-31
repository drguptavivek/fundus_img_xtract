from flask import Blueprint

bp = Blueprint("verify_encounter_set", __name__, url_prefix="/verify_encounter_set", template_folder="templates")

from . import routes
