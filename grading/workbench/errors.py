"""Typed errors exposed by the workbench façade."""

from __future__ import annotations


class WorkbenchError(ValueError):
    code = "workbench_error"
    status_code = 422
    reload_required = False

    def __init__(self, message: str, *, details: dict[str, object] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "field_errors": {},
            "reload_required": self.reload_required,
            "details": self.details,
        }


class WorkbenchNotFound(WorkbenchError):
    code = "not_found"
    status_code = 404


class WorkbenchAccessDenied(WorkbenchError):
    code = "not_eligible"
    status_code = 403


class ActiveSessionExists(WorkbenchError):
    code = "active_session_exists"
    status_code = 409


class NoEligibleWork(WorkbenchError):
    code = "no_eligible_work"
    status_code = 404


class LeaseConflict(WorkbenchError):
    code = "lease_conflict"
    status_code = 409


class SessionExpired(WorkbenchError):
    code = "session_expired"
    status_code = 409
    reload_required = True


class SessionTokenInvalid(WorkbenchError):
    code = "session_token_invalid"
    status_code = 403


class SessionSuperseded(WorkbenchError):
    code = "session_superseded"
    status_code = 409
    reload_required = True


class ConfigurationChanged(WorkbenchError):
    code = "configuration_changed"
    status_code = 409
    reload_required = True


class DraftValidationError(WorkbenchError):
    code = "draft_validation_error"
    status_code = 422


class AnnotationValidationError(WorkbenchError):
    code = "annotation_validation_error"
    status_code = 422


class AnnotationPolicyChanged(AnnotationValidationError):
    code = "annotation_policy_changed"
    status_code = 409
    reload_required = True
