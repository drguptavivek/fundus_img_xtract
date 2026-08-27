# Authorization API

The authorization API is implemented as a cutover-staged surface in
`api/authorization.py`. It is deliberately not imported by `api/__init__.py`
until the route/action manifest has no unclassified live endpoints and the old
authorization engines are removed. This prevents authorization-v2 from
becoming a parallel production decision source.

The deterministic foundation catalogue is generated under
`docs/policy/generated/`. Its banner is normative: these artifacts describe
the staged foundation, not the authorization currently enforcing live routes.

All responses are JSON. Session-authenticated mutations require the normal
Flask-WTF CSRF token in `X-CSRFToken`. Authorization denials expose only
`{"error":{"code":"not_authorized"}}`; internal predicates and supporting
grant identifiers are never returned.

Every exact endpoint must provide a typed positive resource reference and the
session channel declared by its catalogue action. Missing or ambiguous target
information denies before a database lookup. Set/list APIs also deny when the
exact action depends on row-specific evidence that their SQL provider cannot
reproduce; a broad scope filter is never substituted.

## GET `/api/authorization/me/capabilities`

Returns only the authenticated actor's potential canonical capabilities and
the scope types supporting each capability. Exact-resource submission checks
remain mandatory; this projection is not an authorization receipt.

## GET `/api/authorization/me/workspaces`

Returns active classical Lab Units and project sites reached by the actor's
current grants. Project and classical ownership remain separate.

## GET `/api/authorization/me/upload-options`

Returns the intersection of current grants, active exact upload-profile
assignments, and active targets. It exposes the authorized profile identity,
not the profile's internal configuration. The upload domain service separately
validates kind, disease, camera, area, encounter-set type, and mydriatic
compatibility.

## GET `/api/authorization/catalogue`

Returns the DTO projection of canonical actions and roles. Requires an active
session and `authorization.catalogue.view` (system `admin`). No query
parameters are accepted.

## GET `/api/authorization/grants`

Returns only grants that the caller may delegate at a containing scope. The
query applies scope and delegable-role predicates in SQL before ORM rows are
loaded. Self-grants are excluded. Requires `authorization.grants.view`.

Successful response:

```json
{"data":{"items":[{"id":17,"user_id":24,"role":"analytics_viewer","scope":{"scope_type":"lab_unit","scope_id":4,"hospital_id":1,"lab_unit_id":4,"project_id":null,"project_lab_unit_id":null},"description":"Programme analyst","active":true}]}}
```

## POST `/api/authorization/grants`

Creates or reactivates the one historical row for a logical grant. Requires
`authorization.grants.manage`, exact target-user and scope resolution,
delegation containment, an active target user, and non-self allocation. The
audit row is written in the same transaction; audit failure rolls back the
mutation.

```json
{
  "user_id": 24,
  "role": "analytics_viewer",
  "scope_type": "lab_unit",
  "scope_id": 4,
  "description": "Programme analyst"
}
```

`role` and `scope_type` are allowlisted canonical enums. `scope_id` is a stable
database ID and must be `null` only for system scope. Request-supplied lineage
such as hospital or project IDs is rejected; the server reloads it.

## PATCH `/api/authorization/grants/{grant_id}`

Changes `description` and/or `active`; grants are never deleted. Setting
`description` to `null` clears it. The service locks the grant, reloads the
actor and target, rechecks exact authorization and delegation, then writes the
mutation and audit in one transaction.

```json
{"description": null, "active": false}
```

Validation failures return HTTP 400 with `invalid_request`. Missing or
unauthorized targets return the same generic HTTP 403 denial response.
