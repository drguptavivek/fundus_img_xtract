"""Validation and extraction for live Remidio gateway responses."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .errors import RemidioValidationError
from .schemas import RemidioExamPayload, RemidioImagePayload, RemidioReportPayload


JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
PII_KEYS = {"email", "employeeId", "firstName", "lastName", "dateOfBirth"}
SECRET_KEY_PARTS = ("authorization", "auth", "token", "password", "signature", "googleaccessid")
URL_KEYS = {"url", "downloadUrl", "downloadURL", "signedUrl", "signedURL"}


def normalize_date(value: str) -> str:
    """Accept DD-MM-YYYY or YYYY-MM-DD and return Remidio's DD-MM-YYYY."""
    value = (value or "").strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    raise RemidioValidationError("Dates must be DD-MM-YYYY or YYYY-MM-DD.")


def normalize_device_type(value: str) -> str:
    value = (value or "").strip().upper()
    if not value:
        raise RemidioValidationError("remidio_device_type is required.")
    return value


def require_gateway_ok(body: Any) -> Any:
    if not isinstance(body, dict):
        raise RemidioValidationError("Remidio response was not a JSON object.")
    status = body.get("status")
    if isinstance(status, dict) and status.get("statusCode") not in {None, "OK"}:
        message = status.get("message") or "Remidio gateway returned a non-OK status."
        raise RemidioValidationError(str(message))
    if "data" not in body:
        raise RemidioValidationError("Remidio response did not contain data.")
    return body["data"]


def require_token(body: Any) -> str:
    data = require_gateway_ok(body)
    token = _find_token(data)
    if not token:
        raise RemidioValidationError("Remidio token response did not contain a token.")
    return token


def require_list_data(body: Any) -> list[Any]:
    data = require_gateway_ok(body)
    if not isinstance(data, list):
        raise RemidioValidationError("Remidio response data was not a list.")
    return data


def sanitize_for_storage(value: Any, *, key: str | None = None) -> Any:
    """Remove obvious secrets and direct identity values from stored raw snapshots."""
    if isinstance(value, dict):
        return {str(k): sanitize_for_storage(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_storage(item, key=key) for item in value]
    if isinstance(value, str):
        key_lower = (key or "").lower()
        if key in PII_KEYS:
            return "[redacted]"
        if key in URL_KEYS:
            return "[redacted-url]"
        if any(part in key_lower for part in SECRET_KEY_PARTS):
            return "[redacted]"
        if JWT_RE.match(value.strip()):
            return "[redacted-jwt]"
    return value


def extract_sites(body: Any) -> list[dict[str, Any]]:
    sites = require_list_data(body)
    normalized: list[dict[str, Any]] = []
    for site in sites:
        if not isinstance(site, dict):
            continue
        site_id = site.get("siteId")
        if site_id is None:
            continue
        normalized.append(
            {
                "remidio_site_id": str(site_id),
                "site_name": _optional_str(site.get("siteName")),
                "site_domain": _optional_str(site.get("siteDomain")),
                "raw_json": sanitize_for_storage(site),
            }
        )
    return normalized


def extract_exam_payloads(data: list[Any], *, site_custom_identifier: str | None, pull_source: str) -> list[RemidioExamPayload]:
    payloads: list[RemidioExamPayload] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        exam_details = item.get("examDetails")
        if not isinstance(exam_details, dict):
            continue
        exam_id = exam_details.get("id")
        if exam_id is None:
            continue

        patient_details = item.get("patientDetails") if isinstance(item.get("patientDetails"), dict) else {}
        device_types = _device_types(exam_details.get("deviceType"))
        exam_date_ms = _optional_int(exam_details.get("examDate"))

        payloads.append(
            RemidioExamPayload(
                remidio_exam_id=str(exam_id),
                site_custom_identifier=site_custom_identifier,
                remidio_numeric_site_id=_optional_str(patient_details.get("siteId")),
                remidio_patient_id=_optional_str(patient_details.get("id")),
                remidio_patient_mrn=_optional_str(patient_details.get("mrn")),
                exam_local_id=_optional_str(exam_details.get("localId")),
                exam_custom_id=_optional_str(exam_details.get("examCustomId")),
                device_types=device_types,
                exam_state=_optional_str(exam_details.get("examState")),
                exam_date_ms=exam_date_ms,
                exam_date=_datetime_from_ms(exam_date_ms),
                pull_source=pull_source,
                raw_json=sanitize_for_storage(deepcopy(item)),
                images=_extract_images(item.get("images")),
                reports=_extract_reports(item),
            )
        )
    return payloads


def _find_token(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("clientAuthToken", "client_auth_token", "accessToken", "access_token", "authToken", "auth_token", "token"):
            token = value.get(key)
            if isinstance(token, str) and token.strip():
                return token.strip()
        for item in value.values():
            token = _find_token(item)
            if token:
                return token
    if isinstance(value, list):
        for item in value:
            token = _find_token(item)
            if token:
                return token
    return None


def _extract_images(images: Any) -> list[RemidioImagePayload]:
    if not isinstance(images, dict):
        return []
    extracted: list[RemidioImagePayload] = []
    for bucket_name, bucket in images.items():
        if not isinstance(bucket, dict):
            continue
        for variant_name, image_list in bucket.items():
            if not isinstance(image_list, list):
                continue
            for image in image_list:
                if not isinstance(image, dict) or image.get("id") is None:
                    continue
                extracted.append(
                    RemidioImagePayload(
                        remidio_image_id=str(image["id"]),
                        device_type=_optional_str(image.get("deviceType")),
                        image_bucket=_optional_str(bucket_name),
                        image_variant=_optional_str(variant_name),
                        laterality=_optional_str(image.get("laterality")),
                        field=_optional_str(image.get("field")),
                        quality=_optional_str(image.get("quality")),
                        width=_optional_int(image.get("width")),
                        height=_optional_int(image.get("height")),
                        remidio_path=_optional_str(image.get("path")),
                        remidio_thumbnail_path=_optional_str(image.get("thumbnailPath")),
                        raw_json=sanitize_for_storage(deepcopy(image)),
                    )
                )
    return extracted


def _extract_reports(exam: dict[str, Any]) -> list[RemidioReportPayload]:
    reports: list[RemidioReportPayload] = []
    for key, value in exam.items():
        if key == "images":
            continue
        if isinstance(value, dict) and key.lower().endswith("report") and value.get("id") is not None:
            reports.append(_report_from_dict(value, key))
        elif isinstance(value, list) and key.lower().endswith(("reports", "report")):
            for item in value:
                if isinstance(item, dict) and item.get("id") is not None:
                    reports.append(_report_from_dict(item, key))
    return reports


def _report_from_dict(value: dict[str, Any], report_type: str) -> RemidioReportPayload:
    generated_date_ms = _optional_int(value.get("generatedDate"))
    return RemidioReportPayload(
        remidio_report_id=str(value["id"]),
        report_type=report_type,
        report_local_id=_optional_str(value.get("localId")),
        generated_date_ms=generated_date_ms,
        generated_at=_datetime_from_ms(generated_date_ms),
        remidio_path=_optional_str(value.get("path")),
        raw_json=sanitize_for_storage(deepcopy(value)),
    )


def _device_types(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip().upper()]
    return []


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _datetime_from_ms(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
