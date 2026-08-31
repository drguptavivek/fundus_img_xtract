from io import BytesIO

import pytest
from PIL import Image

from iitk_api_integration.client import IITKClient
from iitk_api_integration.errors import IITKConfigError, IITKRemoteError


class Response:
    def __init__(self, *, body=None, content=b"", status_code=200, headers=None):
        self.body = body
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    def json(self):
        return self.body

    def iter_content(self, chunk_size):
        _ = chunk_size
        yield self.content

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 12), color="blue").save(output, format="JPEG")
    return output.getvalue()


def test_client_parses_partial_session_and_image_inventory():
    session_payload = {"sessionId": "s-1", "startedAt": "2026-08-01T01:30:00Z", "status": "partial", "imageCount": 1, "mrn": "M-1", "capturedPositions": ["primary", "consent"], "futureSessionField": {"value": 7}}
    image_payload = {"filename": "private.jpg", "position": "primary", "sizeBytes": 100, "contentType": "image/jpeg", "capturedAt": "2026-08-01T01:31:00Z", "futureImageField": ["kept"]}
    inventory_payload = {"sessionId": "s-1", "mode": "closeup", "images": [image_payload], "futureInventoryField": True}
    transport = Session(
        Response(body={"sessions": [session_payload], "nextPageToken": "next"}),
        Response(body=inventory_payload),
        Response(content=jpeg(), headers={"content-type": "image/jpeg"}),
    )
    client = IITKClient("secret", base_url="https://iitk.test", min_request_interval_seconds=0, session=transport)

    page = client.list_sessions(limit=1)
    inventory = client.list_images("s-1")
    content = client.get_image("s-1", "private.jpg")

    assert page.sessions[0].status == "partial"
    assert page.sessions[0].captured_positions == ("primary", "consent")
    assert page.next_page_token == "next"
    assert inventory.images[0].position == "primary"
    assert page.sessions[0].raw_payload == session_payload
    assert inventory.raw_payload == inventory_payload
    assert inventory.images[0].raw_payload == image_payload
    assert content.startswith(b"\xff\xd8\xff")
    assert transport.calls[0][1]["headers"] == {"Authorization": "Bearer secret"}


def test_client_protects_token_transport_and_remote_body():
    with pytest.raises(IITKConfigError, match="HTTPS"):
        IITKClient("secret", base_url="http://remote.test")

    client = IITKClient("secret", base_url="https://iitk.test", min_request_interval_seconds=0, session=Session(Response(status_code=403, body={"error": "forbidden", "message": "private MRN"})))
    with pytest.raises(IITKRemoteError) as exc_info:
        client.list_sessions()
    assert "private MRN" not in str(exc_info.value)


def test_client_retries_one_transient_request_after_five_seconds(monkeypatch):
    transient = Response(status_code=503, body={"error": "unavailable"})
    transport = Session(
        transient,
        Response(body={"sessions": [], "nextPageToken": None}),
    )
    sleeps = []
    monkeypatch.setattr("iitk_api_integration.client.time.sleep", sleeps.append)
    client = IITKClient("secret", base_url="https://iitk.test", min_request_interval_seconds=0, session=transport)

    assert client.list_sessions().sessions == ()
    assert sleeps == [5.0]
    assert len(transport.calls) == 2
    assert transient.closed is True


def test_client_does_not_retry_nontransient_client_error(monkeypatch):
    transport = Session(Response(status_code=404, body={"error": "not_found"}))
    sleeps = []
    monkeypatch.setattr("iitk_api_integration.client.time.sleep", sleeps.append)
    client = IITKClient("secret", base_url="https://iitk.test", min_request_interval_seconds=0, session=transport)

    with pytest.raises(IITKRemoteError):
        client.list_sessions()
    assert sleeps == []
    assert len(transport.calls) == 1
