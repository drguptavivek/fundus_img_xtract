from dataclasses import asdict, dataclass


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
    capabilities: WorkspaceCapabilitiesDTO
    read_only_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["read_only_reasons"] = list(self.read_only_reasons)
        return payload
