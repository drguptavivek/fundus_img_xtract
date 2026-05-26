from remidio_api_integration.client import RemidioClient
from remidio_api_integration.schemas import RemidioSecrets


class FakeResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    def json(self):
        return {"status": {"statusCode": "OK"}, "data": []}


class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        return FakeResponse()


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
