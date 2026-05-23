"""Fetch one sanitized Remidio examination sample using app-stored credentials.

This is a discovery helper for schema planning. It reads the encrypted
RemidioConnection from the application database, calls
getPatientWithLastExam, and writes sanitized output under REMIDIO_Samples.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_transaction_manager import transaction_scope
from models import RemidioConnection
from remidio_api_integration.client import RemidioClient
from remidio_api_integration.service import _secrets


DEFAULT_OUTPUT_DIR = Path("REMIDIO_Samples")
JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
PII_KEYS = {
    "dateOfBirth",
    "email",
    "employeeId",
    "firstName",
    "lastName",
    "middleName",
    "mobile",
    "mobileNumber",
    "mrn",
    "name",
    "patientName",
    "phone",
}
SECRET_KEY_PARTS = ("authorization", "auth", "password", "signature", "token", "googleaccessid")
SIGNED_URL_KEYS = {"downloadURL", "downloadUrl", "path", "signedURL", "signedUrl", "thumbnailPath", "url"}


def main() -> int:
    args = parse_args()
    with transaction_scope() as db:
        connection = (
            db.query(RemidioConnection)
            .filter(RemidioConnection.name == args.connection_name)
            .one_or_none()
        )
        if connection is None:
            raise SystemExit(f"Remidio connection not found: {args.connection_name}")
        secrets = _secrets(connection)

    client = RemidioClient(secrets)
    payload = fetch_latest_patient_exam(client, site_identifier=args.site_custom_id, mrn=args.mrn)
    sanitized = sanitize(payload)
    output = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "connection_name": args.connection_name,
        "site_custom_id": args.site_custom_id,
        "mrn": "[redacted]",
        "endpoint": "getPatientWithLastExam",
        "summary": summarize_exam_payload(sanitized),
        "payload": sanitized,
    }
    output_path = write_output(output, args.output_dir)
    print(f"Wrote sanitized examination sample: {output_path}")
    print(json.dumps(output["summary"], indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-name", default="r.pcenter")
    parser.add_argument("--site-custom-id", default="rpc_comoph_2")
    parser.add_argument("--mrn", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def sanitize(value: Any, *, key: str | None = None) -> Any:
    key_lower = (key or "").lower()
    pii_keys_lower = {item.lower() for item in PII_KEYS}
    if key in PII_KEYS or key_lower in pii_keys_lower:
        return "[redacted]"
    if any(part in key_lower for part in SECRET_KEY_PARTS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item, key=key) for item in value]
    if isinstance(value, str):
        if JWT_RE.match(value.strip()):
            return "[redacted-jwt]"
        if key in SIGNED_URL_KEYS and value.startswith(("http://", "https://")):
            return redact_url(value)
    return value


def fetch_latest_patient_exam(client: RemidioClient, *, site_identifier: str, mrn: str) -> dict[str, Any]:
    path = (
        "/api/gateway/getPatientWithLastExam/"
        f"{quote(site_identifier, safe='')}/"
        f"{quote(mrn, safe='')}"
    )
    url = f"{client.secrets.base_url.rstrip()}{path}"
    response = requests.get(url, headers=client._gateway_headers(include_bearer=True), timeout=30)
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:2000]
    return {
        "_http": {
            "status_code": response.status_code,
            "reason": response.reason,
            "content_type": response.headers.get("content-type"),
        },
        "body": body,
    }


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "[redacted-url]"
    if not parts.scheme or not parts.netloc:
        return "[redacted-url]"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "[redacted-query]", ""))


def summarize_exam_payload(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("body") if isinstance(payload, dict) else payload
    data = body.get("data") if isinstance(body, dict) else None
    exam = data if isinstance(data, dict) else {}
    exam_details = exam.get("examDetails") if isinstance(exam.get("examDetails"), dict) else {}
    patient_details = exam.get("patientDetails") if isinstance(exam.get("patientDetails"), dict) else {}
    images = exam.get("images") if isinstance(exam.get("images"), dict) else {}

    image_summary: dict[str, Any] = {}
    image_count = 0
    for bucket_name, bucket in images.items():
        if not isinstance(bucket, dict):
            continue
        bucket_summary: dict[str, int] = {}
        for variant_name, rows in bucket.items():
            count = len(rows) if isinstance(rows, list) else 0
            bucket_summary[str(variant_name)] = count
            image_count += count
        image_summary[str(bucket_name)] = bucket_summary

    report_keys = []
    for key, value in exam.items():
        key_lower = str(key).lower()
        if key == "images":
            continue
        if key_lower.endswith("report") and isinstance(value, dict):
            report_keys.append(str(key))
        if key_lower.endswith("reports") and isinstance(value, list):
            report_keys.append(str(key))

    return {
        "http": payload.get("_http") if isinstance(payload.get("_http"), dict) else None,
        "gateway_status_code": body.get("status", {}).get("statusCode") if isinstance(body, dict) and isinstance(body.get("status"), dict) else None,
        "top_level_keys": sorted(body.keys()) if isinstance(body, dict) else [],
        "exam_keys": sorted(exam.keys()),
        "exam_detail_keys": sorted(exam_details.keys()),
        "patient_detail_keys": sorted(patient_details.keys()),
        "device_type": exam_details.get("deviceType"),
        "exam_state": exam_details.get("examState"),
        "image_bucket_counts": image_summary,
        "image_count": image_count,
        "report_keys": sorted(report_keys),
    }


def write_output(output: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"{timestamp}_remidio_exam_{safe_slug(output['site_custom_id'])}.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return path


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "sample"


if __name__ == "__main__":
    raise SystemExit(main())
