"""Markdown, HTML, and matrix renderers driven by catalogue DTOs."""

from __future__ import annotations

from html import escape

from authz_v2.domain.descriptions import AuthorizationCatalogueDTO


def catalogue_markdown(catalogue: AuthorizationCatalogueDTO) -> str:
    lines = [
        "# Authorization v2 foundation catalogue",
        "",
        "> Foundation artifact: implemented and verified, but not registered in the live application. Live enforcement remains on the legacy engines until the atomic cutover.",
        "",
        "## Actions",
        "",
    ]
    for action in catalogue.actions:
        lines.extend(
            [
                f"### `{action.action}`",
                "",
                action.description,
                "",
                f"Resource: `{action.resource_type}`; disclosure: `{action.disclosure_class}`; audit: `{action.audit_mode}`.",
                "",
            ]
        )
        for path in action.paths:
            lines.append(f"- `{path.name}`: " + ", ".join(path.requirements))
        lines.append("")
    lines.extend(["## Roles", ""])
    for role in catalogue.roles:
        scopes = ", ".join(f"`{scope}`" for scope in sorted(role.permitted_scope_types))
        lines.append(f"- `{role.role}` — {role.purpose}. Scopes: {scopes}.")
    return "\n".join(lines).rstrip() + "\n"


def catalogue_html(catalogue: AuthorizationCatalogueDTO) -> str:
    action_rows = "".join(
        "<tr>"
        f"<td><code>{escape(action.action)}</code></td>"
        f"<td>{escape(action.resource_type)}</td>"
        f"<td>{escape(', '.join(path.name for path in action.paths))}</td>"
        f"<td>{escape(action.disclosure_class)}</td>"
        f"<td>{escape(action.audit_mode)}</td>"
        "</tr>"
        for action in catalogue.actions
    )
    role_rows = "".join(
        "<tr>"
        f"<td><code>{escape(role.role)}</code></td>"
        f"<td>{escape(role.purpose)}</td>"
        f"<td>{escape(', '.join(sorted(role.permitted_scope_types)))}</td>"
        "</tr>"
        for role in catalogue.roles
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Authorization v2 foundation catalogue</title></head>'
        "<body><h1>Authorization v2 foundation catalogue</h1>"
        "<p><strong>Foundation artifact:</strong> implemented and verified, but not registered in the live application. Live enforcement remains on the legacy engines until the atomic cutover.</p>"
        "<h2>Actions</h2>"
        "<table><thead><tr><th>Action</th><th>Resource</th><th>Paths</th><th>Disclosure</th><th>Audit</th></tr></thead>"
        f"<tbody>{action_rows}</tbody></table><h2>Roles</h2>"
        "<table><thead><tr><th>Role</th><th>Purpose</th><th>Scopes</th></tr></thead>"
        f"<tbody>{role_rows}</tbody></table></body></html>"
    )


def role_action_matrix(
    catalogue: AuthorizationCatalogueDTO,
) -> tuple[tuple[str, ...], ...]:
    rows = [("action", "resource_type", "paths", "disclosure", "audit")]
    rows.extend(
        (
            action.action,
            action.resource_type,
            "|".join(path.name for path in action.paths),
            action.disclosure_class,
            action.audit_mode,
        )
        for action in catalogue.actions
    )
    return tuple(rows)
