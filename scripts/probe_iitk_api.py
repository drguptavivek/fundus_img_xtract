"""Safely probe the IITK/AIIMS Image Capture annotation API.

The probe is deliberately read-only. It prints sanitized structural summaries
to stdout and never writes response snapshots or downloaded image bytes.

Examples:
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py list-sessions --limit 3
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py list-images --session-id SESSION_ID
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py image-info --session-id SESSION_ID --filename FILENAME
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py sample --limit 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / "develop.config.env"
DEFAULT_BASE_URL = "https://asia-south1-imagecapture-6b306.cloudfunctions.net"
DEFAULT_LIMIT = 3
MAX_LIMIT = 200
MAX_IMAGE_BYTES = 50 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30
GAZE_POSITIONS = {
    "primary",
    "up",
    "up_right",
    "right",
    "down_right",
    "down",
    "down_left",
    "left",
    "up_left",
    "composite",
}
SESSION_POSITIONS = GAZE_POSITIONS | {"consent"}
SESSION_KEYS = {
    "sessionId",
    "site",
    "mode",
    "startedAt",
    "capturedPositions",
    "expectedPositions",
    "status",
    "imageCount",
    "mrn",
    "age",
    "eye",
    "gender",
    "diagnosis",
    "diagnosisOther",
    "clinicianUid",
}
IMAGE_KEYS = {"filename", "position", "sizeBytes", "contentType", "capturedAt"}


class ProbeError(RuntimeError):
    """Base class for safe, user-facing probe failures."""


class ConfigError(ProbeError):
    """Raised when local probe configuration is invalid or incomplete."""


class ContractError(ProbeError):
    """Raised when an upstream response violates the required contract shape."""


class RemoteError(ProbeError):
    """Raised for non-successful upstream HTTP responses."""

    def __init__(self, status_code: int, error_code: str | None = None) -> None:
        self.status_code = status_code
        self.error_code = error_code
        suffix = f" ({error_code})" if error_code else ""
        super().__init__(f"IITK API returned HTTP {status_code}{suffix}.")


@dataclass(frozen=True)
class ImageBytesInfo:
    content_type: str
    byte_length: int
    width: int
    height: int
    image_format: str
    sha256: str


class IITKProbeClient:
    """Minimal read-only client for the documented IITK API endpoints."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        normalized_url = base_url.rstrip("/")
        parsed = urlsplit(normalized_url)
        is_local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        if not parsed.netloc or (parsed.scheme != "https" and not is_local_http):
            raise ConfigError("IITK base URL must use HTTPS (plain HTTP is allowed only for localhost tests).")
        if not token.strip():
            raise ConfigError("IITK_TOKEN is missing or empty.")
        self.base_url = normalized_url
        self.token = token.strip()
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def list_sessions(
        self,
        *,
        site: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        status: str | None = None,
        limit: int = DEFAULT_LIMIT,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        if limit < 1 or limit > MAX_LIMIT:
            raise ConfigError(f"limit must be between 1 and {MAX_LIMIT}.")
        if status not in {None, "complete", "partial"}:
            raise ConfigError("status must be complete or partial.")
        _validate_iso_date(from_date, "from-date")
        _validate_iso_date(to_date, "to-date")
        params = _drop_empty(
            {
                "site": site,
                "from": from_date,
                "to": to_date,
                "status": status,
                "limit": limit,
                "pageToken": page_token,
            }
        )
        body = self._get_json("/listSessions", params=params)
        if not isinstance(body.get("sessions"), list):
            raise ContractError("listSessions response must contain a sessions array.")
        if body.get("nextPageToken") is not None and not isinstance(body.get("nextPageToken"), str):
            raise ContractError("listSessions nextPageToken must be a string or null.")
        return body

    def list_images(self, *, session_id: str) -> dict[str, Any]:
        normalized_session_id = _required_string(session_id, "session-id")
        body = self._get_json("/listImages", params={"sessionId": normalized_session_id})
        if not isinstance(body.get("sessionId"), str):
            raise ContractError("listImages response must contain sessionId.")
        if not isinstance(body.get("images"), list):
            raise ContractError("listImages response must contain an images array.")
        return body

    def image_info(self, *, session_id: str, filename: str) -> ImageBytesInfo:
        normalized_session_id = _required_string(session_id, "session-id")
        normalized_filename = _required_string(filename, "filename")
        response = self._request(
            "/image",
            params={"sessionId": normalized_session_id, "filename": normalized_filename},
            stream=True,
        )
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type not in {"image/jpeg", "image/jpg"}:
            raise ContractError(f"image response content type must be image/jpeg, got {content_type or 'missing'}.")
        content_length = _optional_int(response.headers.get("content-length"))
        if content_length is not None and content_length > MAX_IMAGE_BYTES:
            raise ContractError(f"image response exceeds the {MAX_IMAGE_BYTES}-byte safety limit.")

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise ContractError(f"image response exceeds the {MAX_IMAGE_BYTES}-byte safety limit.")
            chunks.append(chunk)
        content = b"".join(chunks)
        if not content.startswith(b"\xff\xd8\xff"):
            raise ContractError("image response does not have a JPEG signature.")
        try:
            with Image.open(BytesIO(content)) as image:
                image.load()
                image_format = str(image.format or "").upper()
                width, height = image.size
        except (UnidentifiedImageError, OSError) as exc:
            raise ContractError("image response could not be decoded as an image.") from exc
        if image_format != "JPEG":
            raise ContractError(f"decoded image format must be JPEG, got {image_format or 'unknown'}.")
        return ImageBytesInfo(
            content_type=content_type,
            byte_length=len(content),
            width=width,
            height=height,
            image_format=image_format,
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def _get_json(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = self._request(path, params=params)
        try:
            body = response.json()
        except ValueError as exc:
            raise ContractError("IITK API returned a non-JSON response.") from exc
        if not isinstance(body, dict):
            raise ContractError("IITK API JSON response must be an object.")
        return body

    def _request(self, path: str, **kwargs: Any) -> requests.Response:
        response = self.session.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=self.timeout_seconds,
            **kwargs,
        )
        if response.status_code < 200 or response.status_code >= 300:
            error_code = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    error_code = _safe_enum(body.get("error"))
            except ValueError:
                pass
            raise RemoteError(response.status_code, error_code)
        return response


def summarize_sessions(body: dict[str, Any]) -> dict[str, Any]:
    summaries = []
    for index, value in enumerate(body["sessions"], start=1):
        if not isinstance(value, dict):
            raise ContractError(f"sessions[{index}] must be an object.")
        session_id = value.get("sessionId")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ContractError(f"sessions[{index}].sessionId must be a non-empty string.")
        positions = value.get("capturedPositions")
        position_warnings: list[str] = []
        if positions is not None:
            if not isinstance(positions, list) or not all(isinstance(item, str) for item in positions):
                raise ContractError(f"sessions[{index}].capturedPositions must be an array of strings.")
            unknown_positions = set(positions) - SESSION_POSITIONS
            if unknown_positions:
                position_warnings.append(f"{len(unknown_positions)} unrecognized capture position value(s)")
        summaries.append(
            {
                "row": index,
                "session_ref": _opaque_ref(session_id),
                "keys": sorted(value),
                "unexpected_keys": sorted(set(value) - SESSION_KEYS),
                "status": _safe_enum(value.get("status")),
                "site": _safe_enum(value.get("site")),
                "mode": _safe_enum(value.get("mode")),
                "eye": _safe_enum(value.get("eye")),
                "gender": _safe_enum(value.get("gender")),
                "diagnosis": _safe_enum(value.get("diagnosis")),
                "captured_positions": (
                    [item if item in SESSION_POSITIONS else "[unrecognized]" for item in positions]
                    if isinstance(positions, list)
                    else None
                ),
                "expected_positions": _optional_int(value.get("expectedPositions")),
                "image_count": _optional_int(value.get("imageCount")),
                "started_at_type": _type_name(value.get("startedAt")),
                "patient_fields": {
                    "mrn": "[redacted]" if value.get("mrn") not in {None, ""} else None,
                    "age_type": _type_name(value.get("age")),
                    "diagnosis_other": "[redacted]" if value.get("diagnosisOther") not in {None, ""} else None,
                    "clinician_uid": "[redacted]" if value.get("clinicianUid") not in {None, ""} else None,
                },
                "warnings": position_warnings,
            }
        )
    return {
        "session_count": len(summaries),
        "has_next_page": bool(body.get("nextPageToken")),
        "sessions": summaries,
    }


def summarize_images(body: dict[str, Any]) -> dict[str, Any]:
    images = []
    seen_positions: set[str] = set()
    for index, value in enumerate(body["images"], start=1):
        if not isinstance(value, dict):
            raise ContractError(f"images[{index}] must be an object.")
        filename = value.get("filename")
        position = value.get("position")
        if not isinstance(filename, str) or not filename.strip():
            raise ContractError(f"images[{index}].filename must be a non-empty string.")
        if not isinstance(position, str) or not position.strip():
            raise ContractError(f"images[{index}].position must be a non-empty string.")
        warnings = []
        safe_position = position if position in GAZE_POSITIONS else "[unrecognized]"
        if safe_position == "[unrecognized]":
            warnings.append("unrecognized gaze position value")
        if safe_position in seen_positions:
            warnings.append(f"duplicate gaze value: {safe_position}")
        seen_positions.add(safe_position)
        images.append(
            {
                "row": index,
                "filename_ref": _opaque_ref(filename),
                "extension": Path(filename).suffix.lower(),
                "position": safe_position,
                "size_bytes": _optional_int(value.get("sizeBytes")),
                "content_type": _safe_media_type(value.get("contentType")),
                "captured_at_type": _type_name(value.get("capturedAt")),
                "keys": sorted(value),
                "unexpected_keys": sorted(set(value) - IMAGE_KEYS),
                "warnings": warnings,
            }
        )
    return {
        "session_ref": _opaque_ref(body["sessionId"]),
        "mode": _safe_enum(body.get("mode")),
        "image_count": len(images),
        "images": images,
    }


def run_sample(client: IITKProbeClient, args: argparse.Namespace) -> dict[str, Any]:
    sessions_body = client.list_sessions(**_session_filters(args))
    sessions_summary = summarize_sessions(sessions_body)
    complete = next(
        (
            row
            for row in sessions_body["sessions"]
            if isinstance(row, dict) and row.get("status") == "complete" and isinstance(row.get("sessionId"), str)
        ),
        None,
    )
    if complete is None:
        raise ContractError("The sample page did not contain a complete session to inspect.")
    session_id = complete["sessionId"]
    images_body = client.list_images(session_id=session_id)
    images_summary = summarize_images(images_body)
    first_jpeg = next(
        (
            row
            for row in images_body["images"]
            if isinstance(row, dict)
            and isinstance(row.get("filename"), str)
            and str(row.get("contentType") or "").lower() in {"image/jpeg", "image/jpg"}
        ),
        None,
    )
    if first_jpeg is None:
        raise ContractError("The selected complete session did not contain a JPEG image entry.")
    image_info = client.image_info(session_id=session_id, filename=first_jpeg["filename"])
    return {
        "command": "sample",
        "sessions": sessions_summary,
        "selected_session_ref": _opaque_ref(session_id),
        "image_inventory": images_summary,
        "validated_image": {
            "filename_ref": _opaque_ref(first_jpeg["filename"]),
            "content_type": image_info.content_type,
            "byte_length": image_info.byte_length,
            "width": image_info.width,
            "height": image_info.height,
            "format": image_info.image_format,
            "sha256": image_info.sha256,
            "saved_to_disk": False,
        },
    }


def _session_filters(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "site": args.site,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "status": args.status,
        "limit": args.limit,
        "page_token": args.page_token,
    }


def _drop_empty(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in {None, ""}}


def _validate_iso_date(value: str | None, label: str) -> None:
    if value is None:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{label} must use YYYY-MM-DD.") from exc


def _required_string(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ConfigError(f"{label} is required.")
    return normalized


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opaque_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _safe_enum(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 100:
        return None
    if not all(character.isalnum() or character in {"_", "-", " ", "."} for character in normalized):
        return None
    return normalized


def _safe_media_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized.count("/") != 1 or len(normalized) > 100:
        return None
    if not all(character.isalnum() or character in {"/", ".", "+", "-"} for character in normalized):
        return None
    return normalized


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list-sessions", "list-images", "image-info", "sample"))
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--base-url")
    parser.add_argument("--site")
    parser.add_argument("--from-date", help="ISO date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="ISO date (YYYY-MM-DD)")
    parser.add_argument("--status", choices=("complete", "partial"))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--page-token")
    parser.add_argument("--session-id")
    parser.add_argument("--filename")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file.exists():
        load_dotenv(args.env_file, override=False)
    token = os.getenv("IITK_TOKEN", "").strip()
    base_url = (args.base_url or os.getenv("IITK_BASE_URL") or DEFAULT_BASE_URL).strip()
    try:
        client = IITKProbeClient(token=token, base_url=base_url)
        if args.command == "list-sessions":
            result = {"command": args.command, **summarize_sessions(client.list_sessions(**_session_filters(args)))}
        elif args.command == "list-images":
            result = {
                "command": args.command,
                **summarize_images(client.list_images(session_id=_required_string(args.session_id, "session-id"))),
            }
        elif args.command == "image-info":
            session_id = _required_string(args.session_id, "session-id")
            filename = _required_string(args.filename, "filename")
            info = client.image_info(session_id=session_id, filename=filename)
            result = {
                "command": args.command,
                "session_ref": _opaque_ref(session_id),
                "filename_ref": _opaque_ref(filename),
                "content_type": info.content_type,
                "byte_length": info.byte_length,
                "width": info.width,
                "height": info.height,
                "format": info.image_format,
                "sha256": info.sha256,
                "saved_to_disk": False,
            }
        else:
            result = run_sample(client, args)
    except ConfigError as exc:
        print(json.dumps({"error": str(exc), "kind": "configuration"}, indent=2, sort_keys=True))
        return 2
    except RemoteError as exc:
        print(
            json.dumps(
                {"error": str(exc), "kind": "remote", "status_code": exc.status_code, "error_code": exc.error_code},
                indent=2,
                sort_keys=True,
            )
        )
        return 3
    except ContractError as exc:
        print(json.dumps({"error": str(exc), "kind": "contract"}, indent=2, sort_keys=True))
        return 4
    except requests.RequestException as exc:
        print(json.dumps({"error": type(exc).__name__, "kind": "network"}, indent=2, sort_keys=True))
        return 5

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
