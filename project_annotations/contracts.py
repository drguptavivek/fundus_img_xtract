from dataclasses import asdict, dataclass


SUPPORTED_TOOL_KEYS = ("box", "rect", "polygon", "brush_mask", "ellipse", "pyramid")
NON_PROJECT_POLICY_REVISION = 1
SUPPORTED_LOCALIZATIONS = frozenset({"none", "box", "segmentation", "box_or_segmentation"})


@dataclass(frozen=True)
class ProjectClassInputDTO:
    id: int | None
    key: str
    localization: str
    display_order: int
    multiple_instances: bool
    active: bool


@dataclass(frozen=True)
class PolicyUpdateDTO:
    revision: int
    enabled: bool
    default_localization: str
    preferred_tool: str
    enabled_tools: tuple[str, ...]
    project_classes: tuple[ProjectClassInputDTO, ...]


@dataclass(frozen=True)
class FeaturePolicyDTO:
    localization: str
    preferred_tool: str
    allowed_tools: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["allowed_tools"] = list(self.allowed_tools)
        return payload


@dataclass(frozen=True)
class ResolvedProjectClassDTO:
    id: int
    key: str
    localization: str
    display_order: int
    multiple_instances: bool
    active: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AnnotationContextDTO:
    policy_source: str
    project_id: int | None
    enabled: bool
    revision: int
    enabled_tools: tuple[str, ...]
    default_feature_policy: FeaturePolicyDTO
    project_classes: tuple[ResolvedProjectClassDTO, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_source": self.policy_source,
            "project_id": self.project_id,
            "enabled": self.enabled,
            "revision": self.revision,
            "enabled_tools": list(self.enabled_tools),
            "default_feature_policy": self.default_feature_policy.to_dict(),
            "project_classes": [item.to_dict() for item in self.project_classes],
        }
