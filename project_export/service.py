"""Public service of the project export module.

``export_package`` and ``export_options`` are the only entry points routes
and jobs need; scope resolution, identifier rules and DuckDB writing stay inside.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select

from models import Hospital, LabUnit, Project
from project_configuration.models import ProjectLabUnit

from .dto import ExportRequest, ExportResult
from .exceptions import ProjectExportInvalid, ProjectExportNotFound
from .package import build_package
from .tables import ExportScope


def resolve_scope(db, request: ExportRequest) -> tuple[ExportScope, str, str]:
    """Return ``(scope, code, title)`` for a request.

    Projects use every lab mapped to them (active or not). With no project, selected lab units win (and must
    belong to any selected hospitals); hospitals alone mean all their lab units.
    """
    if request.project_id is not None:
        project = db.get(Project, request.project_id)
        if project is None:
            raise ProjectExportNotFound(f"Project {request.project_id} was not found.")
        # Every lab mapped to the project, active or not: an admin export must not drop data because a
        # lab's project mapping was later deactivated.
        labs = frozenset(db.execute(
            select(ProjectLabUnit.lab_unit_id).where(ProjectLabUnit.project_id == project.id)
        ).scalars())
        code, title = project.code, project.title
    else:
        query = select(LabUnit.id)
        if request.hospital_ids:
            query = query.where(LabUnit.hospital_id.in_(request.hospital_ids))
        if request.lab_unit_ids:
            query = query.where(LabUnit.id.in_(request.lab_unit_ids))
        labs = frozenset(db.execute(query).scalars())
        if not labs:
            raise ProjectExportInvalid("The selected hospitals and lab units match no lab units.")
        code, title = "", "No project (classical uploads)"
    return ExportScope(request.project_id, labs, labs if request.include_identifiers else frozenset()), code, title


def export_package_for_scope(db, scope: ExportScope, directory: Path, *, stem: str, code: str, title: str) -> ExportResult:
    """Write ``<directory>/<stem>.duckdb`` for an already-resolved scope (admin requests and sync grants share this)."""
    path = Path(directory) / f"{re.sub(r'[^A-Za-z0-9_-]+', '_', stem)}.duckdb"
    counts = build_package(db, scope, path, project_code=code, project_title=title)
    return ExportResult(path, counts)


def export_package(db, request: ExportRequest, directory: Path) -> ExportResult:
    """Write the DuckDB package for ``request`` into ``directory``."""
    scope, code, title = resolve_scope(db, request)
    stem = f"project_{code or request.project_id}" if request.project_id is not None else "no_project"
    return export_package_for_scope(db, scope, directory, stem=stem, code=code, title=title)


def export_workbook(db, request: ExportRequest, directory: Path) -> ExportResult:
    """Excel workbook of the same package (built from the DuckDB file); the DuckDB file is not kept."""
    from .xlsx import write_workbook

    directory = Path(directory)
    work = directory / "duckdb"
    work.mkdir()
    built = export_package(db, request, work)
    path = directory / f"{built.path.stem}.xlsx"
    write_workbook(built.path, path)
    return ExportResult(path, built.row_counts)


def export_options(db) -> dict:
    """Choices for the export form: projects, hospitals and lab units."""
    return {
        "projects": [
            {"id": p.id, "code": p.code, "title": p.title, "active": bool(p.active)}
            for p in db.execute(select(Project).order_by(Project.title)).scalars()
        ],
        "hospitals": [
            {"id": h.id, "name": h.name} for h in db.execute(select(Hospital).order_by(Hospital.name)).scalars()
        ],
        "lab_units": [
            {"id": lab.id, "name": lab.name, "hospital_id": lab.hospital_id}
            for lab in db.execute(select(LabUnit).order_by(LabUnit.name)).scalars()
        ],
    }
