"""Admin routes for managing application settings."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from flask import flash, render_template, request, url_for, redirect, current_app
from sqlalchemy.orm import Session

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import AppSetting


SettingMeta = Dict[str, Any]


SETTING_DEFINITIONS: List[SettingMeta] = [
    # Direct upload runtime settings (read from DB at request time)
    {"key": "DIRECT_UPLOAD_MAX_FILES", "label": "Direct Upload Max Files", "type": "int", "default": 100, "section": "Direct Upload", "min": 1},
    {"key": "DIRECT_UPLOAD_MAX_FILE_SIZE_MB", "label": "Direct Upload Max File Size (MB)", "type": "int", "default": 10, "section": "Direct Upload", "min": 1},
    {"key": "DIRECT_UPLOAD_ALLOWED_MIMETYPES", "label": "Direct Upload Allowed MIME Types", "type": "csv", "default": ["image/jpeg", "image/png"], "section": "Direct Upload"},
    {"key": "DIRECT_UPLOAD_LIFETIME_QUOTA", "label": "Direct Upload Lifetime Quota (default)", "type": "int", "default": 50, "section": "Direct Upload", "min": 0, "help_text": "Default per-user lifetime file limit; 0 means unlimited unless user-specific quota is set."},

    # Zip upload runtime settings
    {"key": "MAX_FILES_PER_UPLOAD", "label": "ZIP Upload Max Files", "type": "int", "default": 100, "section": "ZIP Upload", "min": 1, "help_text": "Maximum number of ZIP files allowed per upload request."},
    {"key": "PER_FILE_MAX_BYTES", "label": "ZIP Upload Max File Size (bytes)", "type": "int", "default": 10485760, "section": "ZIP Upload", "min": 1, "help_text": "Maximum size per ZIP file in bytes (e.g., 10485760 = 10MB)."},
]


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_csv(value: str | None) -> List[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _stringify(meta: SettingMeta, value: Any) -> str:
    if meta["type"] == "bool":
        return "true" if bool(value) else "false"
    if meta["type"] == "csv":
        if isinstance(value, list):
            return ",".join(value)
        return str(value or "")
    return str(value) if value is not None else ""


def _coerce(meta: SettingMeta, raw_value: str | None) -> Tuple[Any, str | None]:
    """Coerce raw value to expected type; returns (parsed_value, error_message)."""
    if raw_value is None:
        return None, None

    value_type = meta["type"]
    label = meta.get("label", meta["key"])

    if value_type == "int":
        parsed = _to_int(raw_value.strip())
        if parsed is None:
            return None, f"{label} must be a whole number."
        min_value = meta.get("min")
        if min_value is not None and parsed < min_value:
            return None, f"{label} must be at least {min_value}."
        return parsed, None

    if value_type == "bool":
        parsed_bool = _parse_bool(raw_value)
        if parsed_bool is None:
            return None, f"{label} must be true/false."
        return parsed_bool, None

    if value_type == "csv":
        parsed_list = _parse_csv(raw_value)
        return parsed_list or [], None

    # default: string
    return raw_value.strip(), None


def _resolve_setting(db_session: Session, meta: SettingMeta) -> Dict[str, Any]:
    """Resolve current value and source for a setting."""
    default_value = meta["default"]
    env_raw = os.getenv(meta.get("env_var", meta["key"]))
    env_value, env_error = _coerce(meta, env_raw)
    env_source = "environment" if env_raw is not None else "default"

    fallback_value = env_value if env_error is None and env_raw is not None else default_value

    setting = db_session.get(AppSetting, str(meta["key"]))
    if setting:
        db_value, db_error = _coerce(meta, setting.value)
        if db_error:
            current_app.logger.warning(
                "Invalid value for %s in app_settings (%s). Falling back to %s",
                meta["key"], setting.value, fallback_value
            )
        else:
            return {
                **meta,
                "value": _stringify(meta, db_value),
                "source": "database",
                "env_value": _stringify(meta, env_value) if env_raw is not None else None,
                "default_value": _stringify(meta, default_value),
            }

    return {
        **meta,
        "value": _stringify(meta, fallback_value),
        "source": env_source if env_error is None else "default",
        "env_value": _stringify(meta, env_value) if env_raw is not None else None,
        "default_value": _stringify(meta, default_value),
    }


@roles_required("admin")
def admin_settings():
    """View and update configuration stored in app_settings (non-secret keys)."""
    with get_db_session() as db_session:
        if request.method == "POST":
            errors: List[str] = []
            updates: Dict[str, str] = {}

            for meta in SETTING_DEFINITIONS:
                raw_value = request.form.get(meta["key"], "")
                parsed, error = _coerce(meta, raw_value)
                if error:
                    errors.append(error)
                    continue
                updates[meta["key"]] = _stringify(meta, parsed)

            if errors:
                for err in errors:
                    flash(err, "danger")
            else:
                for meta in SETTING_DEFINITIONS:
                    value_str = updates[meta["key"]]
                    setting = db_session.get(AppSetting, meta["key"])
                    if setting is None:
                        setting = AppSetting(
                            key=meta["key"],
                            value=value_str,
                            value_type=meta.get("type", "string"),
                        )
                        db_session.add(setting)
                    else:
                        setting.value = value_str
                        setting.value_type = meta.get("type", "string")
                flash("Settings saved.", "success")
                return redirect(url_for("admin.admin_settings"), code=303)

        resolved_settings = [_resolve_setting(db_session, meta) for meta in SETTING_DEFINITIONS]
        grouped_settings: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for setting in resolved_settings:
            grouped_settings[setting.get("section", "Other")].append(setting)

        # Maintain stable section ordering based on definitions
        section_order: List[str] = []
        for meta in SETTING_DEFINITIONS:
            section = meta.get("section", "Other")
            if section not in section_order:
                section_order.append(section)

        return render_template(
            "admin/admin_settings.html",
            grouped_settings=grouped_settings,
            section_order=section_order,
            active_page="admin_settings",
        )


# Backwards compatibility for old endpoint name
upload_settings = admin_settings
