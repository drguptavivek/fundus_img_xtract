"""Resource adapter registry owned by the application composition root."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from authz_v2.core.actions import Action
from authz_v2.core.choices import ChoiceListDTO
from authz_v2.core.principals import EvaluationFactsDTO, PrincipalDTO
from authz_v2.core.resources import ResourceContextDTO
from authz_v2.repositories.contracts import GrantRecord

Q = TypeVar("Q")

Resolver = Callable[[Any, object], "ResourceTarget | None"]
FactsProvider = Callable[
    [Any, PrincipalDTO, Action, "ResourceTarget", EvaluationFactsDTO],
    EvaluationFactsDTO,
]
QueryScoper = Callable[[Any, PrincipalDTO, Action, tuple[GrantRecord, ...], Q], Q]
ChoiceProvider = Callable[
    [Any, PrincipalDTO, Action, tuple[GrantRecord, ...], dict[str, object]],
    ChoiceListDTO,
]


@dataclass(frozen=True)
class ResourceTarget:
    """Server-loaded object plus its resolved authorization context."""

    value: object
    context: ResourceContextDTO


@dataclass(frozen=True)
class ResourceAdapter[Q]:
    resource_type: str
    resolver: Resolver
    query_scoper: QueryScoper[Q]
    facts_provider: FactsProvider | None = None


@dataclass(frozen=True)
class ChoiceAdapter:
    """Bind one projection kind to exactly one governing action."""

    choice_kind: str
    action: Action
    provider: ChoiceProvider


class ResourceRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ResourceAdapter[Any]] = {}

    def register(self, adapter: ResourceAdapter[Any]) -> None:
        if adapter.resource_type in self._adapters:
            raise ValueError(
                f"resource adapter already registered: {adapter.resource_type}"
            )
        self._adapters[adapter.resource_type] = adapter

    def replace(self, adapter: ResourceAdapter[Any]) -> None:
        self._adapters[adapter.resource_type] = adapter

    def get(self, resource_type: str) -> ResourceAdapter[Any] | None:
        return self._adapters.get(resource_type)

    def require(self, resource_type: str) -> ResourceAdapter[Any]:
        adapter = self.get(resource_type)
        if adapter is None:
            raise LookupError(f"unregistered resource type: {resource_type}")
        return adapter

    def types(self) -> frozenset[str]:
        return frozenset(self._adapters)


class ChoiceRegistry:
    """Registry for server-side eligibility and picker projections."""

    def __init__(self) -> None:
        self._providers: dict[str, ChoiceAdapter] = {}

    def register(
        self, choice_kind: str, action: Action, provider: ChoiceProvider
    ) -> None:
        if choice_kind in self._providers:
            raise ValueError(f"choice provider already registered: {choice_kind}")
        self._providers[choice_kind] = ChoiceAdapter(choice_kind, action, provider)

    def get(self, choice_kind: str) -> ChoiceAdapter | None:
        return self._providers.get(choice_kind)


registry = ResourceRegistry()
choice_registry = ChoiceRegistry()
