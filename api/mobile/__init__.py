from flask import Blueprint

mobile_api_bp = Blueprint("mobile_api", __name__, url_prefix="/api/mobile/v1")

from . import auth, context  # noqa: E402,F401
