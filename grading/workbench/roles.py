"""Canonical human grading role slots used by package workflow guards."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


HUMAN_ROLE_SLOTS = frozenset({"resident", "resident2", "arbitrator"})


def has_human_grades(tasks: Iterable[Any]) -> bool:
    """Return whether any task has a persisted human-slot grade."""
    return any(
        grade.role_slot in HUMAN_ROLE_SLOTS
        for task in tasks
        for grade in task.grades
    )
