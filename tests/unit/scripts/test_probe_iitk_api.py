from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from scripts.probe_iitk_api import (
    MAX_IMAGE_BYTES,
    ConfigError,
    ContractError,
    IITKProbeClient,
    RemoteError,
    run_sample,
    summarize_images,
    summarize_sessions,
)


class FakeResponse:
    def __init__(self, *, status_code=200, body=None, headers=None, content=b""):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self._content = content

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def iter_content(self, chunk_size):
        _ = chunk_size
        yield self._content


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def _jpeg_bytes(size=(16, 12)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(output, format="JPEG")
    return output.getvalue()


def _session_payload():
    return {
        "sessions": [
            {
                "sessionId": "bc7838a9-e051-4e6c-a5ab-099794b5b04d",
                "site": "delhi",
                "mode": "closeup",
                "startedAt": "2026-07-21T12:43:38.030Z",
                "capturedPositions": ["primary", "up"],
                "expectedPositions": 9,
                "status": "complete",
                "imageCount": 2,
                "mrn": "107335836",
                "age": 34,
                "eye": "ou",
                "gender": "male",
                "diagnosis": "other",
                "diagnosisOther": "private free text",
            }
        ],
        "nextPageToken": "opaque-page-token",
    }


def _images_payload():
    return {
        "sessionId": "bc7838a9-e051-4e6c-a5ab-099794b5b04d",
        "mode": "closeup",
        "images": [
            {
                "filename": "MRN107335836_20260721_primary.jpg",
                "position": "primary",
                "sizeBytes": 1234,
                "contentType": "image/jpeg",
                "capturedAt": "2026-07-21T07:17:08.004Z",
            }
        ],
    }


def test_client_rejects_plain_http_for_nonlocal_token_transport():
    with pytest.raises(ConfigError, match="must use HTTPS"):
        IITKProbeClient(token="secret", base_url="http://iitk.example.test")

    client = IITKProbeClient(token="secret", base_url="http://localhost:5001")
    assert client.base_url == "http://localhost:5001"


def test_list_sessions_sends_bearer_and_documented_query_params():
    session = FakeSession(FakeResponse(body=_session_payload()))
    client = IITKProbeClient(token="top-secret", base_url="https://iitk.example.test", session=session)

    body = client.list_sessions(
        site="delhi",
        from_date="2026-07-01",
        to_date="2026-07-31",
        status="complete",
        limit=3,
        page_token="next-token",
    )

    assert body["sessions"][0]["status"] == "complete"
    url, kwargs = session.calls[0]
    assert url == "https://iitk.example.test/listSessions"
    assert kwargs["headers"] == {"Authorization": "Bearer top-secret"}
    assert kwargs["params"] == {
        "site": "delhi",
        "from": "2026-07-01",
        "to": "2026-07-31",
        "status": "complete",
        "limit": 3,
        "pageToken": "next-token",
    }


def test_session_and_image_summaries_redact_source_identifiers():
    session_summary = summarize_sessions(_session_payload())
    image_summary = summarize_images(_images_payload())
    rendered = repr({"sessions": session_summary, "images": image_summary})

    assert "107335836" not in rendered
    assert "bc7838a9-e051-4e6c-a5ab-099794b5b04d" not in rendered
    assert "private free text" not in rendered
    assert "MRN107335836_20260721_primary.jpg" not in rendered
    assert session_summary["sessions"][0]["patient_fields"]["mrn"] == "[redacted]"
    assert image_summary["images"][0]["position"] == "primary"
    assert image_summary["images"][0]["content_type"] == "image/jpeg"


def test_session_summary_recognizes_consent_and_hides_unknown_position_values():
    payload = _session_payload()
    payload["sessions"][0]["capturedPositions"] = ["primary", "consent", "MRN107335836"]

    summary = summarize_sessions(payload)["sessions"][0]

    assert summary["captured_positions"] == ["primary", "consent", "[unrecognized]"]
    assert summary["warnings"] == ["1 unrecognized capture position value(s)"]
    assert "107335836" not in repr(summary)


def test_image_info_validates_jpeg_in_memory():
    content = _jpeg_bytes((20, 14))
    session = FakeSession(
        FakeResponse(
            headers={"content-type": "image/jpeg", "content-length": str(len(content))},
            content=content,
        )
    )
    client = IITKProbeClient(token="secret", base_url="https://iitk.example.test", session=session)

    info = client.image_info(session_id="session-1", filename="MRN1_primary.jpg")

    assert info.content_type == "image/jpeg"
    assert info.byte_length == len(content)
    assert (info.width, info.height) == (20, 14)
    assert info.image_format == "JPEG"
    assert len(info.sha256) == 64


def test_image_info_rejects_advertised_oversize_before_reading():
    session = FakeSession(
        FakeResponse(
            headers={"content-type": "image/jpeg", "content-length": str(MAX_IMAGE_BYTES + 1)},
            content=b"",
        )
    )
    client = IITKProbeClient(token="secret", base_url="https://iitk.example.test", session=session)

    with pytest.raises(ContractError, match="safety limit"):
        client.image_info(session_id="session-1", filename="image.jpg")


def test_non_json_or_unsuccessful_responses_fail_without_body_echo():
    bad_json = FakeSession(FakeResponse(body=ValueError("raw private body")))
    client = IITKProbeClient(token="secret", base_url="https://iitk.example.test", session=bad_json)
    with pytest.raises(ContractError, match="non-JSON") as exc_info:
        client.list_sessions()
    assert "private" not in str(exc_info.value)

    forbidden = FakeSession(FakeResponse(status_code=403, body={"error": "forbidden", "message": "private"}))
    client = IITKProbeClient(token="secret", base_url="https://iitk.example.test", session=forbidden)
    with pytest.raises(RemoteError) as exc_info:
        client.list_sessions()
    assert exc_info.value.status_code == 403
    assert "private" not in str(exc_info.value)


def test_sample_reads_sessions_inventory_and_one_image_without_writing():
    content = _jpeg_bytes()
    session = FakeSession(
        FakeResponse(body=_session_payload()),
        FakeResponse(body=_images_payload()),
        FakeResponse(headers={"content-type": "image/jpeg"}, content=content),
    )
    client = IITKProbeClient(token="secret", base_url="https://iitk.example.test", session=session)
    args = SimpleNamespace(site=None, from_date=None, to_date=None, status=None, limit=3, page_token=None)

    result = run_sample(client, args)

    assert result["sessions"]["session_count"] == 1
    assert result["image_inventory"]["image_count"] == 1
    assert result["validated_image"]["saved_to_disk"] is False
    assert len(session.calls) == 3
