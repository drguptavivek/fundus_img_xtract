"""Compatibility imports for the consolidated grading workbench package workflow.

New runtime callers must import the narrow ``grading.workbench.service``
facade. This module remains temporarily for package construction/history
callers while those transports are migrated.
"""

from grading.workbench.package_workflow import (  # noqa: F401
    EncounterSetGradingError,
    EncounterSetSubmissionInputDTO,
    HUMAN_ROLE_SLOTS,
    REVISION_WINDOW,
    StaleEncounterSetPackageError,
    TargetGradeInputDTO,
    editable_tasks,
    package_record_dto,
    ordered_package_tasks,
    reconcile_active_packages,
    reconcile_package_state,
    submit_package,
    visible_tasks,
)

__all__ = [
    "EncounterSetGradingError",
    "EncounterSetSubmissionInputDTO",
    "HUMAN_ROLE_SLOTS",
    "REVISION_WINDOW",
    "StaleEncounterSetPackageError",
    "TargetGradeInputDTO",
    "editable_tasks",
    "package_record_dto",
    "ordered_package_tasks",
    "reconcile_active_packages",
    "reconcile_package_state",
    "submit_package",
    "visible_tasks",
]
