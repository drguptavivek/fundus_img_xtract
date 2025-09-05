from flask import Blueprint
 
bp = Blueprint(
    "direct_uploads",
    __name__,
    template_folder="templates",
)

@bp.record_once
def _on_register(state):
    # Ensure base directory exists on app start
    from models import DIRECT_UPLOAD_DIR  # lazy import to avoid circulars
    DIRECT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    
from . import upload, dashboard, jobs, api, edit_upload, edit_image, save_image  # noqa: E402,F401