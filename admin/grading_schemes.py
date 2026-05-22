"""Admin pages for grading scheme management."""
from __future__ import annotations

from flask import request, render_template

from auth.roles import roles_required
from grading_schemes import service as grading_scheme_service


@roles_required("admin")
def grading_schemes_admin():
    """Render the composite grading schemes workspace."""
    return _render_workspace(
        "admin/partials/grading_schemes/list.html",
        grading_schemes=grading_scheme_service.list_grading_schemes(),
    )


def _render_workspace(workspace_template: str, **context):
    if request.headers.get("HX-Request") == "true":
        return render_template(workspace_template, **context)
    return render_template(
        "admin/grading_schemes.html",
        workspace_template=workspace_template,
        workspace_context=context,
    )


@roles_required("admin")
def grading_schemes_list():
    """Render the dashboard list partial."""
    return _render_workspace(
        "admin/partials/grading_schemes/list.html",
        grading_schemes=grading_scheme_service.list_grading_schemes(),
    )


@roles_required("admin")
def grading_scheme_new():
    """Render the create form partial."""
    return _render_workspace(
        "admin/partials/grading_schemes/form.html",
        mode="create",
        grading_scheme=None,
    )


@roles_required("admin")
def grading_scheme_detail(scheme_id: int):
    """Render one grading scheme detail partial."""
    result = grading_scheme_service.get_grading_scheme(scheme_id)
    if not result.success:
        return render_template(
            "admin/partials/grading_schemes/message.html",
            message=result.message,
            category="danger",
        ), result.status_code
    return _render_workspace(
        "admin/partials/grading_schemes/detail.html",
        grading_scheme=result.payload["grading_scheme"],
    )


@roles_required("admin")
def grading_scheme_edit(scheme_id: int):
    """Render the edit form partial."""
    result = grading_scheme_service.get_grading_scheme(scheme_id)
    if not result.success:
        return render_template(
            "admin/partials/grading_schemes/message.html",
            message=result.message,
            category="danger",
        ), result.status_code
    return _render_workspace(
        "admin/partials/grading_schemes/form.html",
        mode="edit",
        grading_scheme=result.payload["grading_scheme"],
    )
