"""HTTP client for the Remidio Host Gateway API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

import requests

from utils.log_sanitize import sanitize_log_value

from .errors import RemidioRemoteError
from .schemas import RemidioSecrets
from .validation import require_token


class RemidioClient:
    def __init__(self, secrets: RemidioSecrets, *, timeout_seconds: int = 30, session: requests.Session | None = None) -> None:
        self.secrets = secrets
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self._bearer_token: str | None = None
        self._client_auth_token: str | None = None

    def login(self) -> str:
        body = self._request(
            "POST",
            "/api/user/loginUser",
            headers=self._base_headers(),
            json={"emailAddress": self.secrets.email, "password": self.secrets.password},
        )
        self._bearer_token = require_token(body)
        return self._bearer_token

    def get_auth_token(self) -> str:
        bearer_token = self._bearer_token or self.login()
        body = self._request(
            "GET",
            "/api/gateway/getAuthToken",
            headers={**self._base_headers(), "Authorization": f"Bearer {bearer_token}"},
        )
        self._client_auth_token = require_token(body)
        return self._client_auth_token

    def get_sites(self) -> dict[str, Any]:
        return self._request("GET", "/api/gateway/getSites", headers=self._gateway_headers())

    def get_queue_item(self) -> dict[str, Any]:
        return self._request("GET", "/api/gateway/getQueueItem", headers=self._gateway_headers())

    def get_exams_by_date(self, *, start_date: str, end_date: str, site_custom_identifier: str) -> dict[str, Any]:
        path = (
            "/api/gateway/getExamsByDate/"
            f"{quote(start_date, safe='')}/"
            f"{quote(end_date, safe='')}/"
            f"{quote(site_custom_identifier, safe='')}"
        )
        return self._request("GET", path, headers=self._gateway_headers(include_bearer=True))

    def get_patient_with_last_exam(self, *, site_identifier: str, mrn: str) -> dict[str, Any]:
        path = (
            "/api/gateway/getPatientWithLastExam/"
            f"{quote(site_identifier, safe='')}/"
            f"{quote(mrn, safe='')}"
        )
        return self._request("GET", path, headers=self._gateway_headers(include_bearer=True))

    def download_file(self, file_url: str, *, max_bytes: int = 100 * 1024 * 1024) -> tuple[bytes, str | None]:
        """Download a Remidio signed file URL.

        Remidio exam payloads observed in the docs expose file download links in
        `path`/`thumbnailPath`. This method intentionally accepts only absolute
        HTTP(S) links; object keys without a signed URL are not enough to fetch
        bytes safely.
        """
        normalized = (file_url or "").strip()
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RemidioRemoteError("Remidio file path is not a downloadable HTTP(S) URL.")

        try:
            response = self.session.get(normalized, timeout=self.timeout_seconds, stream=True)
        except requests.RequestException as exc:
            raise RemidioRemoteError(f"Remidio file download failed: {sanitize_log_value(exc)}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise RemidioRemoteError("Remidio file download was not successful.", remote_status_code=response.status_code)

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise RemidioRemoteError("Remidio file download exceeded the size limit.")
            chunks.append(chunk)
        return b"".join(chunks), response.headers.get("content-type")

    def _base_headers(self) -> dict[str, str]:
        return {
            "clientName": self.secrets.client_name,
            "clientIdentificationToken": self.secrets.client_identification_token,
        }

    def _gateway_headers(self, *, include_bearer: bool = False) -> dict[str, str]:
        client_auth_token = self._client_auth_token or self.get_auth_token()
        headers = {**self._base_headers(), "clientAuthToken": client_auth_token}
        if include_bearer:
            bearer_token = self._bearer_token or self.login()
            headers["Authorization"] = f"Bearer {bearer_token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.secrets.base_url.rstrip('/')}{path}"
        try:
            response = self.session.request(method, url, timeout=self.timeout_seconds, **kwargs)
        except requests.RequestException as exc:
            raise RemidioRemoteError(f"Remidio request failed: {sanitize_log_value(exc)}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RemidioRemoteError(
                "Remidio returned a non-JSON response.",
                remote_status_code=response.status_code,
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            message = "Remidio request was not successful."
            if isinstance(body, dict):
                status = body.get("status")
                if isinstance(status, dict) and status.get("message"):
                    message = str(status["message"])
            raise RemidioRemoteError(message, remote_status_code=response.status_code)
        return body
