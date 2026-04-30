"""Probe Remidio Host Gateway API responses without acknowledging queue items.

This script is intended for integration discovery. It reads credentials from the
gitignored local development env file and writes sanitized response snapshots to
a gitignored output directory.

Usage:
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py get-sites
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py login
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py get-auth-token
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py queue-peek
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py visits-by-date --site-custom-id SITE --start-date DD-MM-YYYY --end-date DD-MM-YYYY
    UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py latest-patient-exam --site-custom-id SITE --mrn MRN
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / "develop.config.env"
DEFAULT_TOKEN_FILE = PROJECT_ROOT / "token.toml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs/16-NewFeature/Remedio_dashboard_integration/probe_outputs"
DEFAULT_BASE_URL = "https://remidio-backend-india.appspot.com"

SENSITIVE_KEY_PARTS = (
    "authorization",
    "auth",
    "token",
    "password",
    "signature",
    "googleaccessid",
)
PII_KEY_NAMES = {
    "email",
    "employeeId",
    "firstName",
    "lastName",
    "dateOfBirth",
    "mrn",
}
SIGNED_URL_KEYS = {"path", "thumbnailPath", "downloadUrl", "downloadURL", "url"}
TOKEN_VALUE_KEYS = {
    "accessToken",
    "access_token",
    "authToken",
    "auth_token",
    "bearerToken",
    "bearer_token",
    "clientAuthToken",
    "client_auth_token",
    "token",
}
JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")

TOML_ENV_MAP = {
    "base_url": "REMEDIO_BASE_URL",
    "client_name": "REMEDIO_CLIENT_NAME",
    "client_identification_token": "REMEDIO_CLIENT_IDENTIFICATION_TOKEN",
    "email": "REMEDIO_EMAIL",
    "password": "REMEDIO_PASSWORD",
    "bearer_token": "REMEDIO_BEARER_TOKEN",
    "client_auth_token": "REMEDIO_CLIENT_AUTH_TOKEN",
}


class ConfigError(RuntimeError):
    """Raised when required Remidio probe configuration is missing."""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def load_token_toml(path: Path) -> None:
    """Load token.toml values into REMEDIO_* env vars without overriding env."""
    if not path.exists():
        return
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    remedio = data.get("remedio", {})
    if not isinstance(remedio, dict):
        return
    for toml_key, env_key in TOML_ENV_MAP.items():
        value = remedio.get(toml_key)
        if isinstance(value, str) and value.strip() and not os.getenv(env_key):
            os.environ[env_key] = value.strip()


def _toml_string(value: str) -> str:
    """Return a TOML-safe quoted string."""
    return json.dumps(value)


def _required_env(name: str) -> str:
    value = _env(name)
    if value is None:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "[redacted-url]"
    if not parts.scheme or not parts.netloc:
        return value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "[redacted-query]", ""))


def _sanitize(value: Any, *, key: str | None = None) -> Any:
    if key in PII_KEY_NAMES:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item, key=key) for item in value]
    if isinstance(value, str):
        key_lower = (key or "").lower()
        if any(part in key_lower for part in SENSITIVE_KEY_PARTS):
            return "[redacted]"
        if JWT_RE.match(value.strip()):
            return "[redacted-jwt]"
        if key in SIGNED_URL_KEYS and value.startswith(("http://", "https://")):
            return _redact_url(value)
        return value
    return value


def _find_token_value(value: Any, preferred_keys: tuple[str, ...]) -> str | None:
    """Find the first token-like value in a nested API response."""
    if isinstance(value, str) and JWT_RE.match(value.strip()):
        return value.strip()
    if isinstance(value, dict):
        for key in preferred_keys:
            token = value.get(key)
            if isinstance(token, str) and token.strip():
                return token.strip()
        for key, item in value.items():
            if str(key) in TOKEN_VALUE_KEYS and isinstance(item, str) and item.strip():
                return item.strip()
        for item in value.values():
            token = _find_token_value(item, preferred_keys)
            if token:
                return token
    if isinstance(value, list):
        for item in value:
            token = _find_token_value(item, preferred_keys)
            if token:
                return token
    return None


def _headers(*, include_client_auth: bool, bearer_token: str | None = None) -> dict[str, str]:
    headers = {
        "clientName": _required_env("REMEDIO_CLIENT_NAME"),
        "clientIdentificationToken": _required_env("REMEDIO_CLIENT_IDENTIFICATION_TOKEN"),
    }
    if include_client_auth:
        headers["clientAuthToken"] = _required_env("REMEDIO_CLIENT_AUTH_TOKEN")
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


def _request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(method, url, timeout=30, **kwargs)
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return {
        "_raw_body": body,
        "request": {
            "method": method,
            "url": url,
            "headers": _sanitize(kwargs.get("headers") or {}),
            "json": _sanitize(kwargs.get("json")) if "json" in kwargs else None,
        },
        "response": {
            "status_code": response.status_code,
            "reason": response.reason,
            "headers": _sanitize(
                {
                    "content-type": response.headers.get("content-type"),
                    "cache-control": response.headers.get("cache-control"),
                }
            ),
            "body": _sanitize(body),
        },
    }


def _base_url() -> str:
    return (_env("REMEDIO_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")


def call_login() -> dict[str, Any]:
    return _request_json(
        "POST",
        f"{_base_url()}/api/user/loginUser",
        headers=_headers(include_client_auth=False),
        json={
            "emailAddress": _required_env("REMEDIO_EMAIL"),
            "password": _required_env("REMEDIO_PASSWORD"),
        },
    )


def call_get_auth_token() -> dict[str, Any]:
    bearer_token = _env("REMEDIO_BEARER_TOKEN")
    login_result: dict[str, Any] | None = None
    if not bearer_token:
        login_result = call_login()
        body = login_result.get("_raw_body")
        bearer_token = _find_token_value(
            body,
            ("accessToken", "access_token", "authToken", "auth_token", "bearerToken", "bearer_token", "token"),
        )
        if not bearer_token:
            return {
                "error": "Could not locate login bearer token in response. Save it as REMEDIO_BEARER_TOKEN and retry.",
                "login_result": login_result,
            }

    auth_result = _request_json(
        "GET",
        f"{_base_url()}/api/gateway/getAuthToken",
        headers=_headers(include_client_auth=False, bearer_token=bearer_token),
    )
    auth_body = auth_result.get("_raw_body")
    client_auth_token = _find_token_value(
        auth_body,
        ("clientAuthToken", "client_auth_token", "authToken", "auth_token", "token"),
    )
    return {
        "login_result": login_result,
        "auth_result": auth_result,
        "extracted": {
            "bearer_token_found": bool(bearer_token),
            "client_auth_token_found": bool(client_auth_token),
        },
        "_secret_values": {
            "REMEDIO_BEARER_TOKEN": bearer_token,
            "REMEDIO_CLIENT_AUTH_TOKEN": client_auth_token,
        },
    }


def call_get_sites() -> dict[str, Any]:
    return _request_json(
        "GET",
        f"{_base_url()}/api/gateway/getSites",
        headers=_headers(include_client_auth=True),
    )


def call_queue_peek() -> dict[str, Any]:
    result = _request_json(
        "GET",
        f"{_base_url()}/api/gateway/getQueueItem",
        headers=_headers(include_client_auth=True),
    )
    result["safety_note"] = "This script intentionally does not call itemSuccessfullyHandled."
    return result


def call_visits_by_date(args: argparse.Namespace) -> dict[str, Any]:
    start_date = args.start_date or _required_env("REMEDIO_START_DATE")
    end_date = args.end_date or _required_env("REMEDIO_END_DATE")
    site_custom_id = args.site_custom_id or _required_env("REMEDIO_SITE_CUSTOM_ID")
    return _request_json(
        "GET",
        f"{_base_url()}/api/gateway/getExamsByDate/{quote(start_date, safe='')}/{quote(end_date, safe='')}/{quote(site_custom_id, safe='')}",
        headers=_headers(include_client_auth=True, bearer_token=_env("REMEDIO_BEARER_TOKEN")),
    )


def call_latest_patient_exam(args: argparse.Namespace) -> dict[str, Any]:
    site_custom_id = args.site_custom_id or _required_env("REMEDIO_SITE_CUSTOM_ID")
    mrn = args.mrn or _required_env("REMEDIO_MRN")
    return _request_json(
        "GET",
        f"{_base_url()}/api/gateway/getPatientWithLastExam/{quote(site_custom_id, safe='')}/{quote(mrn, safe='')}",
        headers=_headers(include_client_auth=True, bearer_token=_env("REMEDIO_BEARER_TOKEN")),
    )


def write_output(command: str, payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"{timestamp}_{command}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_token_toml(payload: dict[str, Any], token_file: Path) -> Path | None:
    """Write extracted Remidio token values to local token.toml."""
    secret_values = payload.get("result", {}).get("_secret_values")
    if not isinstance(secret_values, dict):
        return None
    bearer_token = secret_values.get("REMEDIO_BEARER_TOKEN")
    client_auth_token = secret_values.get("REMEDIO_CLIENT_AUTH_TOKEN")
    if not bearer_token and not client_auth_token:
        return None

    existing: dict[str, Any] = {}
    if token_file.exists():
        with token_file.open("rb") as fh:
            existing = tomllib.load(fh)
    remedio = existing.get("remedio", {}) if isinstance(existing, dict) else {}
    if not isinstance(remedio, dict):
        remedio = {}

    persisted = {
        "base_url": _env("REMEDIO_BASE_URL", DEFAULT_BASE_URL),
        "client_name": _env("REMEDIO_CLIENT_NAME"),
        "client_identification_token": _env("REMEDIO_CLIENT_IDENTIFICATION_TOKEN"),
        "email": _env("REMEDIO_EMAIL"),
        "password": _env("REMEDIO_PASSWORD"),
        "bearer_token": bearer_token or remedio.get("bearer_token"),
        "client_auth_token": client_auth_token or remedio.get("client_auth_token"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    lines = [
        "# Generated by scripts/probe_remedio_api.py",
        "# Local Remidio API credentials/token cache. Do not commit.",
        "",
        "[remedio]",
    ]
    for key, value in persisted.items():
        if isinstance(value, str) and value.strip():
            lines.append(f"{key} = {_toml_string(value.strip())}")

    token_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return token_file


def _strip_internal_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_internal_secrets(item)
            for key, item in value.items()
            if key not in {"_secret_values", "_raw_body"}
        }
    if isinstance(value, list):
        return [_strip_internal_secrets(item) for item in value]
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("login", "get-auth-token", "get-sites", "queue-peek", "visits-by-date", "latest-patient-exam"),
        nargs="?",
        default="get-sites",
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--site-custom-id")
    parser.add_argument("--mrn")
    parser.add_argument("--start-date", help="DD-MM-YYYY")
    parser.add_argument("--end-date", help="DD-MM-YYYY")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file.exists():
        load_dotenv(args.env_file, override=True)
    load_token_toml(args.token_file)

    commands = {
        "login": call_login,
        "get-auth-token": call_get_auth_token,
        "get-sites": call_get_sites,
        "queue-peek": call_queue_peek,
        "visits-by-date": lambda: call_visits_by_date(args),
        "latest-patient-exam": lambda: call_latest_patient_exam(args),
    }

    try:
        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "command": args.command,
            "result": commands[args.command](),
        }
    except ConfigError as exc:
        print(str(exc))
        return 2
    except requests.RequestException as exc:
        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "command": args.command,
            "network_error": str(exc),
        }

    token_output_path = write_token_toml(payload, args.token_file)
    payload = _strip_internal_secrets(payload)
    output_path = write_output(args.command, payload, args.output_dir)
    status = payload.get("result", {}).get("response", {}).get("status_code")
    if status is None:
        status = payload.get("result", {}).get("auth_result", {}).get("response", {}).get("status_code")
    if status is not None:
        print(f"{args.command}: HTTP {status}")
    print(f"Wrote sanitized output: {output_path}")
    if token_output_path:
        print(f"Updated local token cache: {token_output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
