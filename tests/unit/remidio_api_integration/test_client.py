import logging

import requests

from remidio_api_integration.client import RemidioClient
from remidio_api_integration.errors import RemidioRemoteError
from remidio_api_integration.schemas import RemidioDownloadContext, RemidioSecrets


class FakeResponse:
    def __init__(self, *, status_code=200, body=None, text="", headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {"status": {"statusCode": "OK"}, "data": []}
        self.text = text
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or FakeResponse()

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        return self.response

    def get(self, url, **kwargs):
        self.calls.append({"method": "GET", "url": url, "kwargs": kwargs})
        return self.response


class FailingDownloadSession(FakeSession):
    def get(self, url, **kwargs):
        nested = RuntimeError(f"connection reset while requesting {url}")
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}", nested)


def _secrets() -> RemidioSecrets:
    return RemidioSecrets(
        base_url="https://remidio.example.test",
        client_name="PACS_GATEWAY",
        client_identification_token="client-token",
        email="user@example.test",
        password="password",
    )


def test_get_exams_by_date_can_request_signed_file_paths():
    session = FakeSession()
    client = RemidioClient(_secrets(), session=session)
    client._client_auth_token = "gateway-token"
    client._bearer_token = "bearer-token"

    client.get_exams_by_date(
        start_date="01-04-2026",
        end_date="02-04-2026",
        site_custom_identifier="rpc_comoph_2",
        include_file_paths=True,
    )

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith("/api/gateway/getExamsByDate/01-04-2026/02-04-2026/rpc_comoph_2")
    assert call["kwargs"]["params"] == {"includeFilePaths": "true"}
    assert call["kwargs"]["headers"]["clientAuthToken"] == "gateway-token"
    assert call["kwargs"]["headers"]["Authorization"] == "Bearer bearer-token"


def test_request_error_snapshot_redacts_signed_urls_and_tokens():
    response = FakeResponse(
        status_code=429,
        body={
            "status": {"statusCode": "RATE_LIMITED", "message": "Too many requests"},
            "data": [
                {
                    "path": "https://storage.googleapis.com/bucket/file.jpg?X-Goog-Signature=secret",
                    "clientAuthToken": "secret-token",
                }
            ],
        },
    )
    session = FakeSession(response=response)
    client = RemidioClient(_secrets(), session=session)

    try:
        client._request("GET", "/api/gateway/getExamsByDate/01-04-2026/02-04-2026/site", params={"includeFilePaths": "true"})
    except RemidioRemoteError as exc:
        assert exc.remote_status_code == 429
        body_preview = exc.response_snapshot["body_preview"]
        assert "Too many requests" in body_preview
        assert "secret-token" not in body_preview
        assert "X-Goog-Signature" not in body_preview
        assert "[redacted-query]" in body_preview
    else:
        raise AssertionError("Expected RemidioRemoteError")


def test_download_failure_never_renders_signed_url_in_error_outputs(caplog):
    signed_url = (
        "https://storage.googleapis.com/private-bucket/image.jpg"
        "?GoogleAccessId=service@example.test&Expires=1786692609&Signature=top-secret"
    )
    client = RemidioClient(_secrets(), session=FailingDownloadSession())
    context = RemidioDownloadContext(
        routing_profile_id=3,
        routing_profile_name="Prospective Retina",
        remidio_api_binding_id=19,
        remidio_api_source_rule_id=7,
        project_id=3,
        project_upload_profile_id=11,
        lab_unit_id=4,
        camera_id=2,
        connection_id=2,
        site_custom_identifier="comoph_4394",
        patient_encounter_id=3936,
        remidio_exam_row_id=812,
        remidio_exam_id="6487588646944768",
        asset_type="image",
        remidio_asset_row_id=11162,
        remidio_asset_id="6025072208773120",
        device_type="FOP",
    )

    with caplog.at_level(logging.WARNING, logger="remidio_api_integration.client"):
        try:
            client.download_file(signed_url, context=context)
        except RemidioRemoteError as exc:
            error_text = str(exc)
            snapshot = exc.response_snapshot
        else:
            raise AssertionError("Expected RemidioRemoteError")

    combined_output = " ".join((caplog.text, error_text, repr(snapshot)))
    assert "top-secret" not in combined_output
    assert "GoogleAccessId" not in combined_output
    assert "Signature" not in combined_output
    assert "private-bucket/image.jpg" not in combined_output
    assert "[redacted-query]" in combined_output
    assert "[redacted-path]" in combined_output
    assert "ConnectionError -> RuntimeError" in combined_output
    assert snapshot["context"] == context.as_dict()
    assert '"routing_profile_id": 3' in caplog.text
    assert '"site_custom_identifier": "comoph_4394"' in caplog.text
    assert '"patient_encounter_id": 3936' in caplog.text
    assert '"remidio_exam_id": "6487588646944768"' in caplog.text
