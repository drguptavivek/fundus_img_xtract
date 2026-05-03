from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from authz.policies import POLICIES

DEFAULT_REGISTRY_DIR = Path(__file__).parent / "actions"


class ActionRegistryError(ValueError):
    """Raised when the authz action registry is invalid."""


@dataclass(frozen=True)
class ActionDefinition:
    """Readable metadata for one authorized application action."""

    name: str
    domain: str
    zone: str
    description: str
    resource_type: str | None
    requires_resource: bool
    source_file: str


def load_action_registry(registry_dir: Path | None = None) -> dict[str, ActionDefinition]:
    """Load all per-domain TOML action registry files."""
    registry_dir = registry_dir or DEFAULT_REGISTRY_DIR
    definitions: dict[str, ActionDefinition] = {}

    for toml_file in sorted(registry_dir.glob("*.toml")):
        payload = tomllib.loads(toml_file.read_text(encoding="utf-8"))
        for raw_action in payload.get("actions", []):
            action = _parse_action(raw_action, toml_file)
            if action.name in definitions:
                existing = definitions[action.name]
                raise ActionRegistryError(
                    f"Duplicate authz action {action.name!r} in {action.source_file}; "
                    f"already defined in {existing.source_file}"
                )
            definitions[action.name] = action

    _validate_policy_coverage(definitions)
    return definitions


def get_action(action: str) -> ActionDefinition:
    """Return one registered action or raise a clear validation error."""
    registry = load_action_registry()
    try:
        return registry[action]
    except KeyError as exc:
        raise ActionRegistryError(f"Unknown authz action {action!r}") from exc


def _parse_action(raw_action: dict[str, Any], toml_file: Path) -> ActionDefinition:
    try:
        name = str(raw_action["name"])
        domain = str(raw_action["domain"])
        zone = str(raw_action["zone"])
        description = str(raw_action["description"])
        requires_resource = bool(raw_action["requires_resource"])
    except KeyError as exc:
        raise ActionRegistryError(f"Missing authz action field {exc.args[0]!r} in {toml_file}") from exc

    resource_type_raw = raw_action.get("resource_type")
    resource_type = str(resource_type_raw) if resource_type_raw is not None else None
    if not name or "." not in name:
        raise ActionRegistryError(f"Invalid authz action name {name!r} in {toml_file}")
    if not domain:
        raise ActionRegistryError(f"Missing authz action domain for {name!r} in {toml_file}")
    if not zone:
        raise ActionRegistryError(f"Missing authz action zone for {name!r} in {toml_file}")
    if not description:
        raise ActionRegistryError(f"Missing authz action description for {name!r} in {toml_file}")
    if requires_resource and not resource_type:
        raise ActionRegistryError(f"Action {name!r} requires resource_type in {toml_file}")

    return ActionDefinition(
        name=name,
        domain=domain,
        zone=zone,
        description=description,
        resource_type=resource_type,
        requires_resource=requires_resource,
        source_file=str(toml_file),
    )


def _validate_policy_coverage(definitions: dict[str, ActionDefinition]) -> None:
    for action in sorted(POLICIES):
        if action not in definitions:
            raise ActionRegistryError(f"Policy action is not registered: {action}")
