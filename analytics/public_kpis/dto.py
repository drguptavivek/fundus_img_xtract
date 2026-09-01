"""DTOs for the public KPI contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PublicKpisDTO:
    """Aggregate system counts that contain no patient-level information."""

    total_images: int
    zip_images: int
    direct_images: int
    encounter_set_images: int
    total_encounters: int
    zip_encounters: int
    encounter_set_encounters: int
    total_ai_gradings: int
    total_gradings: int
    active_projects: int
    total_tasks: int
    disease_task_counts: dict[str, int]
    generated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        return payload
