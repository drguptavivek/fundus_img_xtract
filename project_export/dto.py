"""Request/response contracts of the project export module."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import ProjectExportInvalid

_TRUE = {"1", "true", "yes", "on"}


def _ids(args, name: str) -> tuple[int, ...]:
    try:
        return tuple(sorted({int(value) for value in args.getlist(name)}))
    except ValueError:
        raise ProjectExportInvalid(f"{name} must be integers.") from None


@dataclass(frozen=True)
class ExportRequest:
    """What to export. ``project_id=None`` means encounters that belong to no project."""

    project_id: int | None = None
    hospital_ids: tuple[int, ...] = ()
    lab_unit_ids: tuple[int, ...] = ()
    include_identifiers: bool = False

    def __post_init__(self):
        if self.project_id is None and not (self.hospital_ids or self.lab_unit_ids):
            raise ProjectExportInvalid("Select at least one hospital or lab unit.")

    @classmethod
    def from_query(cls, args, *, project_id: int | None = None) -> "ExportRequest":
        """Build from a query string (``args.getlist`` / ``args.get``); project requests ignore hospital/lab filters."""
        identifiers = str(args.get("identifiers", "")).strip().lower() in _TRUE
        if project_id is not None:
            return cls(project_id=project_id, include_identifiers=identifiers)
        return cls(None, _ids(args, "hospital_id"), _ids(args, "lab_unit_id"), identifiers)

    def audit_details(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "hospital_ids": list(self.hospital_ids),
            "lab_unit_ids": list(self.lab_unit_ids),
            "identifiers": self.include_identifiers,
        }


@dataclass(frozen=True)
class ExportResult:
    path: Path
    row_counts: dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.row_counts.values())
