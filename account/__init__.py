# account/__init__.py
from flask import Blueprint

account_bp = Blueprint(
    "account",
    __name__,
    url_prefix="/account",
    template_folder="templates",
)

from . import routes  # noqa: F401
