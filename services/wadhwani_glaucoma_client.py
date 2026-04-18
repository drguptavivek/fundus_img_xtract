from __future__ import annotations

from typing import Any

import requests


BASE_URL = "https://api-glaucoma.wadhwaniai.org"
INITIALIZE_ENDPOINT = f"{BASE_URL}/api/v1/predictions"


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
    response = requests.post(
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
    response = requests.put(
        upload_url,
        headers={"Content-Type": content_type},
        data=image_bytes,
        timeout=60,
    )
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
    response = requests.post(
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
