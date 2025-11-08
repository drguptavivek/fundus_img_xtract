"""Helpers for loading environment configuration consistently."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

_LOGGER = logging.getLogger(__name__)
_ENV_LOADED = False

_DEFAULT_FILES = (
    "deploy.config.env",
    "deploy.secrets.env",
)


def load_environment(*, force: bool = False, extra_files: Iterable[str] | None = None) -> None:
    """Load configuration files and expand nested references exactly once."""

    global _ENV_LOADED
    if _ENV_LOADED and not force:
        return

    project_root = Path(__file__).resolve().parent.parent
    env_files: list[Path] = []

    # Load default configuration files first
    for name in _DEFAULT_FILES:
        env_files.append(project_root / name)

    # Load development overrides if present (after defaults to override them)
    dev_config_path = project_root / "develop.config.env"
    if dev_config_path.exists():
        env_files.append(dev_config_path)

    env_from_envvar = os.getenv("FUNDUS_ENV_FILES")
    if env_from_envvar:
        env_files.extend(Path(part.strip()) for part in env_from_envvar.split(os.pathsep) if part.strip())

    if extra_files:
        env_files.extend(Path(f) for f in extra_files)

    for env_path in env_files:
        if env_path.exists():
            load_dotenv(env_path, override=True)

    _expand_references()
    _ENV_LOADED = True


def _expand_references() -> None:
    for key, value in list(os.environ.items()):
        if isinstance(value, str) and "${" in value:
            try:
                os.environ[key] = os.path.expandvars(value)
            except Exception as exc:  # pragma: no cover - defensive logging
                _LOGGER.warning("Unable to expand environment variable %s", key, exc_info=exc)


def get_env(key: str, default: str | None = None) -> str | None:
    """Fetch an environment variable after ensuring configuration is loaded."""

    load_environment()
    return os.getenv(key, default)
