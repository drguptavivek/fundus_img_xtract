"""Static authentication and authorization classifications for Flask endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from authz_v2.core.actions import Action
from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.expressions import Expression, SessionChannelRequirement
from authz_v2.core.principals import SessionChannel


def _declares_channel(value, channel: SessionChannel) -> bool:
    if isinstance(value, SessionChannelRequirement):
        return channel in value.channels
    if isinstance(value, Expression):
        return any(_declares_channel(child, channel) for child in value.requirements)
    return False


class EndpointMode(StrEnum):
    PUBLIC = "public"
    SCREEN = "screen"
    PROTECTED = "protected"
    SIGNED_RESOURCE = "signed_resource"
    MOBILE_SESSION = "mobile_session"
    AUTOMATION = "automation"


@dataclass(frozen=True)
class EndpointPolicy:
    mode: EndpointMode
    action: Action
    resolver: str | None = None
    enforcement: str = "central"
    action_variants: tuple[Action, ...] = ()
    binding: str | None = None

    def __post_init__(self) -> None:
        actions = (self.action, *self.action_variants)
        if len(actions) != len(set(actions)):
            raise ValueError("endpoint action variants must be unique")
        definitions = tuple(CATALOGUE[action] for action in actions)
        definition = definitions[0]
        if self.binding:
            if self.resolver:
                raise ValueError(
                    "dynamic endpoint binding cannot also declare a resolver"
                )
            if len(actions) < 2:
                raise ValueError("dynamic endpoint binding requires action variants")
            if any(not item.requires_resource for item in definitions):
                raise ValueError(
                    "dynamic endpoint actions must require exact resources"
                )
        elif self.action_variants:
            raise ValueError("action variants require a dynamic endpoint binding")
        is_public = any(
            path_name == "public" for path_name, _ in definition.authorization_paths
        )
        if self.mode is EndpointMode.PUBLIC and not is_public:
            raise ValueError(
                "public endpoint must use an explicitly public catalogue action"
            )
        if self.mode is not EndpointMode.PUBLIC and is_public:
            raise ValueError("public catalogue action must use public endpoint mode")
        exact_modes = {
            EndpointMode.PUBLIC,
            EndpointMode.PROTECTED,
            EndpointMode.SIGNED_RESOURCE,
            EndpointMode.MOBILE_SESSION,
            EndpointMode.AUTOMATION,
        }
        if (
            self.mode in exact_modes
            and definition.requires_resource
            and not (self.resolver or self.binding)
        ):
            raise ValueError(
                f"{self.mode.value} endpoint requires an exact resource resolver"
            )
        if (
            self.mode in exact_modes
            and definition.requires_resource
            and not self.binding
            and self.resolver != definition.resource_type
        ):
            raise ValueError(
                "endpoint resolver must match the catalogue resource type "
                f"{definition.resource_type}"
            )
        if self.mode is EndpointMode.SCREEN and self.enforcement != "screen_entry":
            raise ValueError("screen endpoint must declare screen_entry enforcement")
        if self.mode is EndpointMode.SCREEN and definition.requires_resource:
            raise ValueError(
                "screen endpoint cannot stand in for an exact resource decision"
            )
        if self.mode in exact_modes and self.enforcement != "central":
            raise ValueError("exact endpoint authorization must be centrally enforced")
        required_channel = {
            EndpointMode.SIGNED_RESOURCE: SessionChannel.SIGNED,
            EndpointMode.MOBILE_SESSION: SessionChannel.MOBILE,
            EndpointMode.AUTOMATION: SessionChannel.AUTOMATION,
        }.get(self.mode)
        if required_channel is not None and any(
            not any(
                _declares_channel(expression, required_channel)
                for _path_name, expression in item.authorization_paths
            )
            for item in definitions
        ):
            raise ValueError(
                f"{self.mode.value} endpoint action must require the "
                f"{required_channel.value} session channel"
            )
