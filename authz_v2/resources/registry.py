"""Resource adapter registry owned by the application composition root."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
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
        self._query_policies: dict[tuple[Action, str], QueryScoper[Any]] = {}
        self._frozen = False
        self._lock = RLock()

    def register(self, adapter: ResourceAdapter[Any]) -> None:
        with self._lock:
            if self._frozen:
                raise RuntimeError("resource registry is frozen")
            existing = self._adapters.get(adapter.resource_type)
            if existing is not None:
                if existing == adapter:
                    return
                raise ValueError(
                    f"conflicting resource adapter: {adapter.resource_type}"
                )
            self._adapters[adapter.resource_type] = adapter

    def replace(self, adapter: ResourceAdapter[Any]) -> None:
        with self._lock:
            if self._frozen:
                raise RuntimeError("resource registry is frozen")
            if adapter.resource_type not in self._adapters:
                raise LookupError(
                    f"unregistered resource type: {adapter.resource_type}"
                )
            self._adapters[adapter.resource_type] = adapter

    def freeze(self) -> None:
        with self._lock:
            self._frozen = True

    def register_query_policy(
        self, action: Action, resource_type: str, policy: QueryScoper[Any]
    ) -> None:
        key = (action, resource_type)
        with self._lock:
            if self._frozen:
                raise RuntimeError("resource registry is frozen")
            existing = self._query_policies.get(key)
            if existing is not None:
                if existing is policy:
                    return
                raise ValueError(
                    f"conflicting query policy: {action.value}/{resource_type}"
                )
            self._query_policies[key] = policy

    def query_policy(
        self, action: Action, resource_type: str
    ) -> QueryScoper[Any] | None:
        return self._query_policies.get((action, resource_type))

    @property
    def frozen(self) -> bool:
        return self._frozen

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
        self._frozen = False
        self._lock = RLock()

    def register(
        self, choice_kind: str, action: Action, provider: ChoiceProvider
    ) -> None:
        adapter = ChoiceAdapter(choice_kind, action, provider)
        with self._lock:
            if self._frozen:
                raise RuntimeError("choice registry is frozen")
            existing = self._providers.get(choice_kind)
            if existing is not None:
                if existing == adapter:
                    return
                raise ValueError(f"conflicting choice provider: {choice_kind}")
            self._providers[choice_kind] = adapter

    def get(self, choice_kind: str) -> ChoiceAdapter | None:
        return self._providers.get(choice_kind)

    def freeze(self) -> None:
        with self._lock:
            self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen
