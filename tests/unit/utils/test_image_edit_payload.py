import base64
from io import BytesIO

import pytest
from PIL import Image

from utils.image_edit_payload import InvalidImageEditPayload, decode_image_edit_payload


def _data_url(image_format: str) -> str:
    output = BytesIO()
    Image.new("RGB", (12, 8), "black").save(output, format=image_format)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/ignored;base64,{encoded}"


@pytest.mark.parametrize(("image_format", "extension"), [("JPEG", ".jpg"), ("PNG", ".png")])
def test_decode_image_edit_payload_uses_actual_format(image_format, extension):
    result = decode_image_edit_payload(_data_url(image_format))

    assert result.extension == extension
    assert result.content


def test_decode_image_edit_payload_rejects_non_image_bytes():
    encoded = base64.b64encode(b"not an image").decode("ascii")

    with pytest.raises(InvalidImageEditPayload):
        decode_image_edit_payload(encoded)
