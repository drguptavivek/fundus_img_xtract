"""Bind saved bulk exports to the authority used to build them.

A fresh permission check cannot redact an already generated file. Downloads
must still cover its entire recorded scope. Legacy files fail closed.
"""
from __future__ import annotations

import json
from pathlib import Path


def _scope_path(export_dir: Path) -> Path:
    # Keep authorization metadata outside the directory exposed for downloads.
    return export_dir.with_name(export_dir.name + ".authorization.json")


def record_export_scope(export_dir: Path, *, project_id: int, user_id: int,
                        lab_unit_ids, pii_lab_unit_ids=(), grant_uuid: str | None = None) -> None:
    payload = {
        "version": 1, "project_id": project_id, "user_id": user_id,
        "grant_uuid": grant_uuid, "lab_unit_ids": sorted(lab_unit_ids),
        "pii_lab_unit_ids": sorted(pii_lab_unit_ids),
    }
    target = _scope_path(export_dir)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(target)


def export_scope_allowed(export_dir: Path, *, project_id: int, user_id: int,
                         lab_unit_ids, pii_lab_unit_ids=(), grant_uuid: str | None = None) -> bool:
    try:
        payload = json.loads(_scope_path(export_dir).read_text(encoding="utf-8"))
        labs = payload["lab_unit_ids"]
        pii_labs = payload["pii_lab_unit_ids"]
        return (
            payload["version"] == 1
            and payload["project_id"] == project_id
            and payload["user_id"] == user_id
            and payload["grant_uuid"] == grant_uuid
            and isinstance(labs, list) and bool(labs)
            and isinstance(pii_labs, list)
            and all(type(item) is int for item in labs + pii_labs)
            and set(labs).issubset(lab_unit_ids)
            and set(pii_labs).issubset(pii_lab_unit_ids)
            and set(pii_labs).issubset(labs)
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False
