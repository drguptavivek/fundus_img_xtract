"""Typed errors of the project export module."""
from __future__ import annotations


class ProjectExportError(Exception):
    """Base class; ``code`` is the machine-readable API error and ``status`` its HTTP status."""

    code = "export_error"
    status = 400


class ProjectExportNotFound(ProjectExportError, LookupError):
    code = "not_found"
    status = 404


class ProjectExportInvalid(ProjectExportError, ValueError):
    code = "invalid"
    status = 400
