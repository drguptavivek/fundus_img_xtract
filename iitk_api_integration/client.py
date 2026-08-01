"""Read-only IITK API client used by browsing and synchronization."""
from __future__ import annotations

from io import BytesIO
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from PIL import Image, UnidentifiedImageError

from .contracts import IITKImageDTO, IITKImageInventory, IITKSessionDTO, IITKSessionPage
from .errors import IITKConfigError, IITKContractError, IITKRemoteError


DEFAULT_BASE_URL = "https://asia-south1-imagecapture-6b306.cloudfunctions.net"
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_PAGE_SIZE = 200


class IITKClient:
    def __init__(self, token: str, *, base_url: str = DEFAULT_BASE_URL, timeout_seconds: int = 30,
                 min_request_interval_seconds: float = 1.0, retry_delay_seconds: float = 5.0, session=None) -> None:
        parsed = urlsplit(base_url.rstrip("/"))
        local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        if not parsed.netloc or (parsed.scheme != "https" and not local_http):
            raise IITKConfigError("IITK base URL must use HTTPS (HTTP is allowed only for localhost tests).")
        if not token.strip():
            raise IITKConfigError("IITK API token is required.")
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout_seconds = timeout_seconds
        self.min_request_interval_seconds = max(float(min_request_interval_seconds), 0.0)
        self.retry_delay_seconds = max(float(retry_delay_seconds), 0.0)
        self._last_request_at: float | None = None
        self.session = session or requests.Session()

    def list_sessions(self, *, site=None, from_date=None, to_date=None, status=None, limit=200, page_token=None) -> IITKSessionPage:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise IITKConfigError("IITK session page limit must be between 1 and 200.")
        params = {"site": site, "from": from_date, "to": to_date, "status": status, "limit": limit, "pageToken": page_token}
        body = self._json("/listSessions", {key: value for key, value in params.items() if value not in {None, ""}})
        rows = body.get("sessions")
        if not isinstance(rows, list):
            raise IITKContractError("IITK listSessions response is missing sessions.")
        token = body.get("nextPageToken")
        if token is not None and not isinstance(token, str):
            raise IITKContractError("IITK nextPageToken must be a string or null.")
        return IITKSessionPage(tuple(_session(row) for row in rows), token)

    def list_images(self, session_id: str) -> IITKImageInventory:
        body = self._json("/listImages", {"sessionId": _required(session_id, "sessionId")})
        images = body.get("images")
        if not isinstance(images, list):
            raise IITKContractError("IITK listImages response is missing images.")
        returned_id = _required(body.get("sessionId"), "sessionId")
        if returned_id != session_id:
            raise IITKContractError("IITK listImages returned a different sessionId.")
        return IITKImageInventory(returned_id, _optional_string(body.get("mode")), tuple(_image(row) for row in images))

    def get_image(self, session_id: str, filename: str) -> bytes:
        response = self._request("/image", {"sessionId": _required(session_id, "sessionId"), "filename": _required(filename, "filename")}, stream=True)
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type not in {"image/jpeg", "image/jpg"}:
            raise IITKContractError("IITK image response is not JPEG.")
        content_length = _optional_int(response.headers.get("content-length"))
        if content_length is not None and content_length > MAX_IMAGE_BYTES:
            raise IITKContractError("IITK image exceeds the 50 MB safety limit.")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise IITKContractError("IITK image exceeds the 50 MB safety limit.")
            chunks.append(chunk)
        content = b"".join(chunks)
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
                if image.format != "JPEG":
                    raise IITKContractError("IITK image payload is not JPEG.")
        except (UnidentifiedImageError, OSError) as exc:
            raise IITKContractError("IITK image payload could not be decoded.") from exc
        return content

    def _json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._request(path, params)
        try:
            body = response.json()
        except ValueError as exc:
            raise IITKContractError("IITK API returned non-JSON data.") from exc
        if not isinstance(body, dict):
            raise IITKContractError("IITK API JSON response must be an object.")
        return body

    def _request(self, path: str, params: dict[str, Any], *, stream: bool = False):
        response = None
        for attempt in range(2):
            self._pace_request()
            try:
                response = self.session.get(
                    f"{self.base_url}{path}", params=params,
                    headers={"Authorization": f"Bearer {self.token}"}, timeout=self.timeout_seconds, stream=stream,
                )
            except requests.RequestException as exc:
                if attempt == 0:
                    time.sleep(self.retry_delay_seconds)
                    continue
                raise IITKRemoteError(0, "network_error") from exc
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 0:
                    response.close()
                    time.sleep(self.retry_delay_seconds)
                    continue
            break
        assert response is not None
        if not 200 <= response.status_code < 300:
            code = None
            try:
                body = response.json()
                candidate = body.get("error") if isinstance(body, dict) else None
                code = candidate if isinstance(candidate, str) and len(candidate) <= 100 else None
            except ValueError:
                pass
            raise IITKRemoteError(response.status_code, code)
        return response

    def _pace_request(self) -> None:
        if self._last_request_at is not None:
            remaining = self.min_request_interval_seconds - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()


def _session(value: Any) -> IITKSessionDTO:
    if not isinstance(value, dict):
        raise IITKContractError("IITK session entry must be an object.")
    positions = value.get("capturedPositions") or []
    if not isinstance(positions, list) or not all(isinstance(item, str) for item in positions):
        raise IITKContractError("IITK capturedPositions must be a string array.")
    status = _required(value.get("status"), "status")
    if status not in {"complete", "partial"}:
        raise IITKContractError("IITK session status must be complete or partial.")
    return IITKSessionDTO(
        session_id=_required(value.get("sessionId"), "sessionId"), site=_optional_string(value.get("site")),
        mode=_optional_string(value.get("mode")), started_at=_required(value.get("startedAt"), "startedAt"),
        captured_positions=tuple(positions), expected_positions=_optional_int(value.get("expectedPositions")),
        status=status, image_count=_optional_int(value.get("imageCount")) or 0,
        mrn=_required(value.get("mrn"), "mrn"), age=_optional_int(value.get("age")),
        eye=_optional_string(value.get("eye")), gender=_optional_string(value.get("gender")),
        diagnosis=_optional_string(value.get("diagnosis")), diagnosis_other=_optional_string(value.get("diagnosisOther")),
        clinician_uid=_optional_string(value.get("clinicianUid")),
    )


def _image(value: Any) -> IITKImageDTO:
    if not isinstance(value, dict):
        raise IITKContractError("IITK image entry must be an object.")
    content_type = _required(value.get("contentType"), "contentType").lower()
    if content_type not in {"image/jpeg", "image/jpg"}:
        raise IITKContractError("IITK image inventory contains a non-JPEG asset.")
    return IITKImageDTO(_required(value.get("filename"), "filename"), _required(value.get("position"), "position"), _optional_int(value.get("sizeBytes")), content_type, _optional_string(value.get("capturedAt")))


def _required(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise IITKContractError(f"IITK {label} is required.")
    return result


def _optional_string(value: Any) -> str | None:
    result = str(value).strip() if value is not None else ""
    return result or None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
