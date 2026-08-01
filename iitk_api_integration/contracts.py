"""Typed transport contracts for the IITK API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IITKSessionDTO:
    session_id: str
    site: str | None
    mode: str | None
    started_at: str
    captured_positions: tuple[str, ...]
    expected_positions: int | None
    status: str
    image_count: int
    mrn: str
    age: int | None
    eye: str | None
    gender: str | None
    diagnosis: str | None
    diagnosis_other: str | None
    clinician_uid: str | None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class IITKImageDTO:
    filename: str
    position: str
    size_bytes: int | None
    content_type: str
    captured_at: str | None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class IITKSessionPage:
    sessions: tuple[IITKSessionDTO, ...]
    next_page_token: str | None


@dataclass(frozen=True)
class IITKImageInventory:
    session_id: str
    mode: str | None
    images: tuple[IITKImageDTO, ...]
    raw_payload: dict[str, Any] | None = None
