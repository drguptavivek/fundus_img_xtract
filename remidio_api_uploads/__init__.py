from flask import Blueprint


bp = Blueprint(
    "remidio_api_uploads",
    __name__,
    template_folder="templates",
)


from . import encounter_set_browser, remidio_api_sync, wadhwani_inference  # noqa: E402,F401
