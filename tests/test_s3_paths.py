from pathlib import Path

import pytest

from models import BASE_DIR
from utils.s3_paths import s3_key_from_local_path, s3_key_from_rel_path


def test_s3_key_from_rel_path():
    assert s3_key_from_rel_path("files/direct_uploads/a.jpg") == "files/direct_uploads/a.jpg"


def test_s3_key_from_local_path():
    local_path = BASE_DIR / "files" / "direct_uploads" / "x" / "a.jpg"
    assert s3_key_from_local_path(local_path) == "files/direct_uploads/x/a.jpg"


def test_s3_key_from_local_path_rejects_outside_base():
    with pytest.raises(ValueError):
        s3_key_from_local_path(Path("/tmp/escape.jpg"))
