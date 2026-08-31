"""Deep pregraded-upload domain interfaces."""

from .dtos import AuthorizedGradeImport, AuthorizedGradeTarget, PregradedImageSelection
from .errors import PregradedUploadError
from .service import (
    authorize_grade_import_targets,
    authorize_image_upload,
    require_pregraded_uploader,
)

__all__ = [
    "AuthorizedGradeImport",
    "AuthorizedGradeTarget",
    "PregradedImageSelection",
    "PregradedUploadError",
    "authorize_grade_import_targets",
    "authorize_image_upload",
    "require_pregraded_uploader",
]
