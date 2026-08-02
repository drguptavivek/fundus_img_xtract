class WorkbenchError(Exception):
    """Base class for expected grading-workbench resolution failures."""


class InvalidWorkbenchTarget(WorkbenchError):
    pass


class WorkbenchTargetNotFound(WorkbenchError):
    pass


class WorkbenchAccessDenied(WorkbenchError):
    pass


class WorkbenchImageUnavailable(WorkbenchError):
    pass
