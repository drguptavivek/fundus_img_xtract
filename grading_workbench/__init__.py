"""Standalone grading workbench domain services."""

from .contracts import WorkspaceDTO
from .service import resolve_task_workspace

__all__ = ["WorkspaceDTO", "resolve_task_workspace"]
