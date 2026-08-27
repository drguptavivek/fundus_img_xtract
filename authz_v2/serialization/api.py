"""JSON-safe serialization for detached authorization DTOs."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum


def serialize_dto(value):
    """Serialize DTOs and primitives without exposing ORM implementation state."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: serialize_dto(getattr(value, item.name))
            for item in fields(value)
            if item.metadata.get("api", True)
        }
    if isinstance(value, dict):
        return {str(key): serialize_dto(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [serialize_dto(item) for item in value]
    raise TypeError(f"unsupported authorization API value: {type(value).__name__}")
