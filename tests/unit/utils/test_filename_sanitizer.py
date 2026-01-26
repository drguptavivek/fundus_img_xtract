import re

import pytest

from utils.filename_sanitizer import sanitize_storage_filename, sanitize_path_component


def test_sanitize_storage_filename_non_ascii_preserves_extension():
    result = sanitize_storage_filename("café.jpg")
    assert result.endswith(".jpg")
    assert re.match(r"^cafe_[0-9a-f]{8}\.jpg$", result)


def test_sanitize_storage_filename_cjk_with_hash():
    result = sanitize_storage_filename("病例图片.png")
    assert result.endswith(".png")
    assert re.match(r"^file_[0-9a-f]{8}\.png$", result)


def test_sanitize_path_component_non_ascii():
    result = sanitize_path_component("临床")
    assert re.match(r"^part_[0-9a-f]{8}$", result)


def test_sanitize_storage_filename_requires_extension_by_default():
    with pytest.raises(ValueError):
        sanitize_storage_filename("nofileext")
