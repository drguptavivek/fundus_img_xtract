"""Regression guards for patient-image consumers outside ``media.routes``."""

import inspect

from api import glaucoma_ai
from services.uploads import mobile


def _assert_authorizes_before_send(function) -> None:
    source = inspect.getsource(inspect.unwrap(function))
    assert "authorize_media_source(" in source
    assert "send_file(" in source
    assert source.index("authorize_media_source(") < source.index("send_file(")


def test_mobile_thumbnail_authorizes_before_reading_or_sending_media() -> None:
    _assert_authorizes_before_send(mobile.get_mobile_direct_upload_thumbnail)


def test_glaucoma_ai_image_authorizes_before_sending_media() -> None:
    _assert_authorizes_before_send(glaucoma_ai.get_glaucoma_ai_upload_image)


def test_glaucoma_ai_thumbnail_authorizes_before_sending_media() -> None:
    _assert_authorizes_before_send(glaucoma_ai.get_glaucoma_ai_upload_thumbnail)
