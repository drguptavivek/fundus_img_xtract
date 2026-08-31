from __future__ import annotations


class PregradedUploadError(ValueError):
    """Safe, typed denial or validation error for pregraded ingestion."""

    def __init__(self, message: str, *, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def invalid(message: str, *, code: str = "invalid_pregraded_upload") -> PregradedUploadError:
    return PregradedUploadError(message, code=code, status_code=400)


def denied(message: str) -> PregradedUploadError:
    return PregradedUploadError(
        message, code="pregraded_upload_denied", status_code=403
    )
