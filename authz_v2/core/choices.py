from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NamedObjectDTO:
    id: int | str
    label: str
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class EligibilityOptionDTO:
    id: int | str
    label: str
    scope_type: str
    project_id: int | None = None
    hospital_id: int | None = None
    lab_unit_id: int | None = None


@dataclass(frozen=True)
class ChoiceListDTO:
    action: str
    options: tuple[NamedObjectDTO | EligibilityOptionDTO, ...]


@dataclass(frozen=True)
class CapabilityDTO:
    action: str
    allowed: bool
    scope_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceOptionDTO:
    id: int | str
    label: str
    scope_type: str
    project_id: int | None = None
    hospital_id: int | None = None
    lab_unit_id: int | None = None


@dataclass(frozen=True)
class UploadOptionDTO(WorkspaceOptionDTO):
    upload_profile_id: int | None = None
