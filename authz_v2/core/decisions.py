from dataclasses import dataclass, field
from datetime import UTC, datetime

from authz_v2.core.principals import RelationshipEvidenceDTO
from authz_v2.core.resources import ScopeDTO


@dataclass(frozen=True)
class DecisionDTO:
    allowed: bool
    action: str
    reason_code: str = "allowed"
    policy_path: str | None = None
    evidence: tuple[int | str, ...] = ()
    relationship_evidence: tuple[RelationshipEvidenceDTO, ...] = field(
        default=(), metadata={"api": False}
    )

    def __bool__(self) -> bool:
        return self.allowed


@dataclass(frozen=True)
class AuthorizationReceiptDTO:
    action: str
    resource_type: str
    resource_id: int | str | None
    policy_path: str
    grant_ids: tuple[int, ...] = ()
    scope: ScopeDTO | None = None
    relationship_evidence: tuple[RelationshipEvidenceDTO, ...] = ()
    break_glass: bool = False
    request_id: str | None = None
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.policy_path:
            raise ValueError("authorization receipt requires a named policy path")
