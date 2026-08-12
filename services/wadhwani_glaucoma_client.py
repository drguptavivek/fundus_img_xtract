from __future__ import annotations

from threading import local
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://api-glaucoma.wadhwaniai.org"
INITIALIZE_ENDPOINT = f"{BASE_URL}/api/v1/predictions"
HTTP_POOL_CONNECTIONS = 4
HTTP_POOL_MAXSIZE = 8
UPLOAD_CONNECT_RETRIES = 3
UPLOAD_RETRY_BACKOFF_SECONDS = 0.5


def _build_http_session() -> requests.Session:
    """Reuse live HTTPS connections and retry idempotent upload failures."""
    retry = Retry(
        total=UPLOAD_CONNECT_RETRIES,
        connect=UPLOAD_CONNECT_RETRIES,
        read=UPLOAD_CONNECT_RETRIES,
        status=UPLOAD_CONNECT_RETRIES,
        allowed_methods=frozenset({"PUT"}),
        status_forcelist=(429, 500, 502, 503, 504),
        backoff_factor=UPLOAD_RETRY_BACKOFF_SECONDS,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=HTTP_POOL_CONNECTIONS,
        pool_maxsize=HTTP_POOL_MAXSIZE,
    )
    session = requests.Session()
    session.mount("https://", adapter)
    return session


_HTTP_SESSION_STATE = local()


def _http_session() -> requests.Session:
    session = getattr(_HTTP_SESSION_STATE, "session", None)
    if session is None:
        session = _build_http_session()
        _HTTP_SESSION_STATE.session = session
    return session


class WadhwaniClientError(RuntimeError):
    def __init__(self, step: str, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.step = step
        self.status_code = status_code
        self.payload = payload


def _headers(client_id: str, bearer_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bearer_token}",
        "X-Client-ID": client_id,
        "Content-Type": "application/json",
    }


def initialize_prediction(
    *,
    client_id: str,
    bearer_token: str,
    request_id: str,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    response = _http_session().post(
        INITIALIZE_ENDPOINT,
        headers=_headers(client_id, bearer_token),
        json={
            "request_id": request_id,
            "files": [{"filename": filename, "content_type": content_type}],
        },
        timeout=15,
    )
    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {}
    if not response.ok:
        raise WadhwaniClientError(
            "initialize",
            f"Initialize request failed with status {response.status_code}",
            status_code=response.status_code,
            payload=payload,
        )
    return payload


def upload_prediction_file(*, upload_url: str, content_type: str, image_bytes: bytes) -> None:
    try:
        response = _http_session().put(
            upload_url,
            headers={"Content-Type": content_type},
            data=image_bytes,
            timeout=60,
        )
    except requests.RequestException as exc:
        # RequestException text includes the presigned URL and its signature.
        raise WadhwaniClientError(
            "upload",
            "Upload request failed after retrying a transient network error",
        ) from exc
    if not response.ok:
        raise WadhwaniClientError(
            "upload",
            f"Upload request failed with status {response.status_code}",
            status_code=response.status_code,
        )


def execute_prediction(
    *,
    client_id: str,
    bearer_token: str,
    prediction_id: str,
    external_request_id: str,
    manifest: list[dict[str, Any]],
) -> dict[str, Any]:
    response = _http_session().post(
        f"{BASE_URL}/api/v1/predictions/{prediction_id}/execute",
        headers=_headers(client_id, bearer_token),
        json={
            "external_request_id": external_request_id,
            "manifest": manifest,
        },
        timeout=30,
    )
    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {}
    if not response.ok:
        raise WadhwaniClientError(
            "execute",
            f"Execute request failed with status {response.status_code}",
            status_code=response.status_code,
            payload=payload,
        )
    return payload
