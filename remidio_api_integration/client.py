"""HTTP client for the Remidio Host Gateway API."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import requests

from utils.log_sanitize import sanitize_log_value

from .errors import RemidioRemoteError
from .schemas import RemidioSecrets
from .validation import require_token, sanitize_for_storage


LOGGER = logging.getLogger("remidio_api_integration.client")
MAX_LOG_BODY_CHARS = 1200


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

    def get_exams_by_date(
        self,
        *,
        start_date: str,
        end_date: str,
        site_custom_identifier: str,
        include_file_paths: bool = False,
    ) -> dict[str, Any]:
        path = (
            "/api/gateway/getExamsByDate/"
            f"{quote(start_date, safe='')}/"
            f"{quote(end_date, safe='')}/"
            f"{quote(site_custom_identifier, safe='')}"
        )
        params = {"includeFilePaths": "true"} if include_file_paths else None
        return self._request("GET", path, headers=self._gateway_headers(include_bearer=True), params=params)

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
            started = perf_counter()
            response = self.session.get(normalized, timeout=self.timeout_seconds, stream=True)
        except requests.RequestException as exc:
            safe_url = _redact_url_query(normalized)
            LOGGER.warning(
                "Remidio file download failed url=%s error=%s",
                sanitize_log_value(safe_url, max_len=500),
                sanitize_log_value(exc, max_len=500),
            )
            raise RemidioRemoteError(
                f"Remidio file download failed: {sanitize_log_value(exc)}",
                response_snapshot={"url": safe_url, "error": sanitize_log_value(exc, max_len=500)},
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            elapsed_ms = int((perf_counter() - started) * 1000)
            snapshot = {
                "url": _redact_url_query(normalized),
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "content_type": response.headers.get("content-type"),
                "content_length": response.headers.get("content-length"),
            }
            LOGGER.warning(
                "Remidio file download unsuccessful status=%s elapsed_ms=%s url=%s content_type=%s content_length=%s",
                sanitize_log_value(response.status_code),
                sanitize_log_value(elapsed_ms),
                sanitize_log_value(snapshot["url"], max_len=500),
                sanitize_log_value(snapshot["content_type"]),
                sanitize_log_value(snapshot["content_length"]),
            )
            raise RemidioRemoteError(
                "Remidio file download was not successful.",
                remote_status_code=response.status_code,
                response_snapshot=snapshot,
            )

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
        params = kwargs.get("params")
        safe_path = _safe_request_path(path, params)
        started = perf_counter()
        try:
            response = self.session.request(method, url, timeout=self.timeout_seconds, **kwargs)
        except requests.RequestException as exc:
            LOGGER.warning(
                "Remidio API request failed method=%s path=%s error=%s",
                sanitize_log_value(method),
                sanitize_log_value(safe_path, max_len=500),
                sanitize_log_value(exc, max_len=500),
            )
            raise RemidioRemoteError(
                f"Remidio request failed: {sanitize_log_value(exc)}",
                response_snapshot={
                    "method": method,
                    "path": safe_path,
                    "error": sanitize_log_value(exc, max_len=500),
                },
            ) from exc
        elapsed_ms = int((perf_counter() - started) * 1000)

        try:
            body = response.json()
        except ValueError as exc:
            snapshot = {
                "method": method,
                "path": safe_path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "content_type": response.headers.get("content-type"),
                "body_preview": sanitize_log_value(response.text, max_len=MAX_LOG_BODY_CHARS),
            }
            LOGGER.warning(
                "Remidio API non-JSON response method=%s path=%s status=%s elapsed_ms=%s content_type=%s body_preview=%s",
                sanitize_log_value(method),
                sanitize_log_value(safe_path, max_len=500),
                sanitize_log_value(response.status_code),
                sanitize_log_value(elapsed_ms),
                sanitize_log_value(snapshot["content_type"]),
                sanitize_log_value(snapshot["body_preview"], max_len=MAX_LOG_BODY_CHARS),
            )
            raise RemidioRemoteError(
                "Remidio returned a non-JSON response.",
                remote_status_code=response.status_code,
                response_snapshot=snapshot,
            ) from exc

        snapshot = _response_snapshot(
            method=method,
            path=safe_path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            body=body,
        )
        if response.status_code < 200 or response.status_code >= 300:
            message = "Remidio request was not successful."
            if isinstance(body, dict):
                status = body.get("status")
                if isinstance(status, dict) and status.get("message"):
                    message = str(status["message"])
            LOGGER.warning(
                "Remidio API unsuccessful response method=%s path=%s status=%s elapsed_ms=%s body=%s",
                sanitize_log_value(method),
                sanitize_log_value(safe_path, max_len=500),
                sanitize_log_value(response.status_code),
                sanitize_log_value(elapsed_ms),
                sanitize_log_value(snapshot["body_preview"], max_len=MAX_LOG_BODY_CHARS),
            )
            raise RemidioRemoteError(message, remote_status_code=response.status_code, response_snapshot=snapshot)

        log_success = LOGGER.info if "getExamsByDate" in path else LOGGER.debug
        log_success(
            "Remidio API response method=%s path=%s status=%s elapsed_ms=%s body_summary=%s",
            sanitize_log_value(method),
            sanitize_log_value(safe_path, max_len=500),
            sanitize_log_value(response.status_code),
            sanitize_log_value(elapsed_ms),
            sanitize_log_value(_payload_summary(body), max_len=500),
        )
        return body


def _safe_request_path(path: str, params: Any) -> str:
    if not params:
        return path
    if isinstance(params, dict):
        query = "&".join(f"{quote(str(key), safe='')}={quote(str(value), safe='')}" for key, value in sorted(params.items()))
    else:
        query = str(params)
    return f"{path}?{query}"


def _response_snapshot(*, method: str, path: str, status_code: int, elapsed_ms: int, body: Any) -> dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "body_preview": _payload_preview(body),
    }


def _payload_preview(value: Any) -> str:
    sanitized = _redact_signed_urls(sanitize_for_storage(value))
    try:
        text = json.dumps(sanitized, ensure_ascii=True, default=str, sort_keys=True)
    except TypeError:
        text = str(sanitized)
    return sanitize_log_value(text, max_len=MAX_LOG_BODY_CHARS)


def _payload_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        data = value.get("data")
        status = sanitize_for_storage(value.get("status")) if "status" in value else None
        summary: dict[str, Any] = {
            "keys": sorted(str(key) for key in value.keys()),
            "status": status,
            "data_type": type(data).__name__ if "data" in value else None,
        }
        if isinstance(data, list):
            summary["data_count"] = len(data)
        elif isinstance(data, dict):
            summary["data_keys"] = sorted(str(key) for key in data.keys())[:20]
        return summary
    if isinstance(value, list):
        return {"type": "list", "count": len(value)}
    return {"type": type(value).__name__}


def _redact_signed_urls(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_signed_urls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_signed_urls(item) for item in value]
    if isinstance(value, str):
        return _redact_url_query(value)
    return value


def _redact_url_query(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.query:
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "[redacted-query]", parsed.fragment))
