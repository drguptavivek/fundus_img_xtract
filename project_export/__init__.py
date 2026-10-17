"""Staged project export package (DuckDB). Public interface: DTOs, errors and two service functions.

Table contracts live in ``schema``; everything else is internal to this module.
"""
from .dto import ExportRequest, ExportResult
from .exceptions import ProjectExportError, ProjectExportInvalid, ProjectExportNotFound
from .service import export_options, export_package, export_package_for_scope, export_workbook, resolve_scope
from .tables import ExportScope

__all__ = [
    "ExportRequest", "ExportResult", "ExportScope", "ProjectExportError", "ProjectExportInvalid",
    "ProjectExportNotFound", "export_options", "export_package", "export_package_for_scope", "export_workbook", "resolve_scope",
]
