from dataclasses import asdict, dataclass
from typing import Any

from project_annotations.contracts import AnnotationContextDTO


@dataclass(frozen=True)
class NamedEntityDTO:
    id: int
    name: str


@dataclass(frozen=True)
class TargetDTO:
    type: str
    ref: str
    slot: str


@dataclass(frozen=True)
class TaskDTO:
    uuid: str
    state: str
    disease: NamedEntityDTO
    lab_unit: NamedEntityDTO


@dataclass(frozen=True)
class ImageDTO:
    uuid: str
    source: str
    url: str
    filename: str | None
    position: int | None = None


@dataclass(frozen=True)
class GradingFeatureDTO:
    id: int
    sr_no: int
    label: str


@dataclass(frozen=True)
class GradingOptionDTO:
    id: int
    impression: str
    display_order: int
    is_active: bool
    is_ungradable: bool
    guidelines: str | None
    features: tuple[GradingFeatureDTO, ...]


@dataclass(frozen=True)
class ExistingGradeDTO:
    id: int
    grading_id: int
    selected_feature_ids: tuple[int, ...]
    comment: str
    annotations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class GradingPanelDTO:
    id: str
    task_uuid: str
    disease: NamedEntityDTO
    grading_scope: str
    target_level: str
    state: str
    read_only: bool
    read_only_reason: str | None
    grades: tuple[GradingOptionDTO, ...]
    existing_grade: ExistingGradeDTO | None


@dataclass(frozen=True)
class WorkspaceCapabilitiesDTO:
    view: bool = True
    annotate: bool = False
    submit: bool = False


@dataclass(frozen=True)
class WorkspaceDTO:
    schema_version: int
    context_revision: str
    target: TargetDTO
    task: TaskDTO
    image: ImageDTO
    images: tuple[ImageDTO, ...]
    active_image_uuid: str
    panels: tuple[GradingPanelDTO, ...]
    annotation_context: AnnotationContextDTO
    capabilities: WorkspaceCapabilitiesDTO
    read_only_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["annotation_context"] = self.annotation_context.to_dict()
        payload["images"] = [asdict(image) for image in self.images]
        payload["panels"] = [asdict(panel) for panel in self.panels]
        payload["read_only_reasons"] = list(self.read_only_reasons)
        return payload
