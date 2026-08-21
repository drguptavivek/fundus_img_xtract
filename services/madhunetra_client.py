"""HTTP client for the synchronous MadhuNetrAI DR-DME screening API."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import requests


PRESIGN_TIMEOUT_SECONDS = 30
UPLOAD_TIMEOUT_SECONDS = 60
SUBMIT_TIMEOUT_SECONDS = 180
# Presign is cheap and idempotent - it reserves upload URLs against a request_id
# that is already durable - so one short retry absorbs a dropped connection
# without risking a duplicate screening.
PRESIGN_RETRY_DELAYS_SECONDS = (3,)
UPLOAD_RETRY_DELAYS_SECONDS = (3, 5)
SUBMIT_RETRY_DELAYS_SECONDS = (2, 10, 30)
TRANSIENT_UPLOAD_STATUSES = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class MadhuNetrAIError(RuntimeError):
    step: str
    code: str
    message: str
    status_code: int | None = None
    detail: Any = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


def _api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Token {token}", "Content-Type": "application/json"}


def _response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        value = response.json() if response.content else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _raise_api_error(step: str, response: requests.Response) -> None:
    payload = _response_payload(response)
    if response.status_code == 401 and "error" not in payload:
        code = "authentication_failed"
    else:
        code = str(payload.get("error") or "http_error")
    retryable = code in {"model_unavailable", "internal_error"} or response.status_code >= 500
    raise MadhuNetrAIError(
        step=step,
        code=code,
        message=f"MadhuNetrAI {step} failed with status {response.status_code}",
        status_code=response.status_code,
        detail=payload.get("detail"),
        retryable=retryable,
    )


class MadhuNetrAIClient:
    """Provider client that never includes the API token on storage uploads."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._session = session or requests.Session()
        self._sleep = sleep

    def presign(self, *, request_id: str, images: list[dict[str, str]]) -> dict[str, Any]:
        """Reserve one upload URL per image, retrying only transient failures.

        Uploads and submit already retry; presign being the sole unprotected step
        meant one dropped connection failed a whole encounter before anything had
        been sent.

        A 4xx still fails immediately - only transport errors and the transient
        statuses are worth a second attempt.
        """
        attempts = 0
        delays = (0, *PRESIGN_RETRY_DELAYS_SECONDS)
        for delay in delays:
            if delay:
                self._sleep(delay)
            attempts += 1
            try:
                response = self._session.post(
                    f"{self.base_url}/api/inference/presign/",
                    headers=_api_headers(self._token),
                    json={"request_id": request_id, "images": images},
                    timeout=PRESIGN_TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                if attempts < len(delays):
                    continue
                raise MadhuNetrAIError(
                    "presign", "network_error", "MadhuNetrAI presign request failed", retryable=True
                ) from exc
            if response.ok:
                return _response_payload(response)
            if response.status_code in TRANSIENT_UPLOAD_STATUSES and attempts < len(delays):
                continue
            _raise_api_error("presign", response)
        raise MadhuNetrAIError(
            "presign", "network_error", "MadhuNetrAI presign request failed", retryable=True
        )

    def upload(self, *, upload_url: str, content_type: str, image_bytes: bytes) -> int:
        """Upload one image, retrying only its transient failures after 3s and 5s."""
        attempts = 0
        delays = (0, *UPLOAD_RETRY_DELAYS_SECONDS)
        for delay in delays:
            if delay:
                self._sleep(delay)
            attempts += 1
            try:
                response = self._session.put(
                    upload_url,
                    headers={"Content-Type": content_type},
                    data=image_bytes,
                    timeout=UPLOAD_TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                if attempts < len(delays):
                    continue
                # Exception text can contain the complete signed URL.
                raise MadhuNetrAIError(
                    "upload", "network_error", "Image upload failed after transient retries", retryable=True
                ) from exc
            if response.ok:
                return attempts
            if response.status_code not in TRANSIENT_UPLOAD_STATUSES or attempts == len(delays):
                raise MadhuNetrAIError(
                    "upload",
                    "upload_failed",
                    f"Image upload failed with status {response.status_code}",
                    status_code=response.status_code,
                    retryable=response.status_code in TRANSIENT_UPLOAD_STATUSES,
                )
        raise AssertionError("unreachable")

    def submit(
        self,
        *,
        request_id: str,
        patient: dict[str, Any],
        images: list[dict[str, str]],
    ) -> dict[str, Any]:
        delays = (0, *SUBMIT_RETRY_DELAYS_SECONDS)
        last_error: MadhuNetrAIError | None = None
        for attempt, delay in enumerate(delays):
            if delay:
                self._sleep(delay)
            try:
                response = self._session.post(
                    f"{self.base_url}/api/inference/",
                    headers=_api_headers(self._token),
                    json={"request_id": request_id, "patient": patient, "images": images},
                    timeout=SUBMIT_TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                last_error = MadhuNetrAIError(
                    "submit", "network_error", "MadhuNetrAI submit outcome is unknown; retry with the same request_id", retryable=True
                )
                if attempt < len(delays) - 1:
                    continue
                raise last_error from exc
            if response.ok:
                return _response_payload(response)
            try:
                _raise_api_error("submit", response)
            except MadhuNetrAIError as exc:
                last_error = exc
                retry_limit = 1 if exc.code == "internal_error" else len(SUBMIT_RETRY_DELAYS_SECONDS)
                if exc.retryable and attempt < retry_limit:
                    continue
                raise
        raise last_error or AssertionError("unreachable")
