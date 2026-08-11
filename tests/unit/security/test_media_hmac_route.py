from __future__ import annotations

import pytest
from werkzeug.exceptions import BadRequest

from media.routes import serve_media_with_hmac


def test_unsigned_hmac_media_request_raises_bad_request_instead_of_logger_error(app):
    with app.test_request_context("/media/test-image-uuid"):
        with pytest.raises(BadRequest):
            serve_media_with_hmac("test-image-uuid")
