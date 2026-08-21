"""Per-upstream fetch adapters behind one field-facing contract."""
from __future__ import annotations

from ..dto import SOURCE_IITK, SOURCE_REMIDIO
from . import iitk, remidio

ADAPTERS = {
    SOURCE_REMIDIO: remidio,
    SOURCE_IITK: iitk,
}


def get_adapter(source: str):
    adapter = ADAPTERS.get((source or "").strip().lower())
    if adapter is None:
        raise KeyError(source)
    return adapter


def configured_sources(db, project_id: int) -> list[str]:
    """Sources actually set up for this project, in a stable order."""
    return [name for name, adapter in ADAPTERS.items() if adapter.is_configured(db, project_id=project_id)]
