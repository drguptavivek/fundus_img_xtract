# Lean authorization rationale and route contract

This note explains the design intent of the current `authz` package and the
minimum expectations for any route, service, list query, or worker that uses it.

## Why the module was redesigned

The previous authorization work became too large because it attempted to model
routes, domain workflows, actions, predicates, caches, and resource details in
one central engine. That made simple policy difficult to read and encouraged
duplicate checks between routes, services, and authorization code.

The lean module follows a smaller rule:

> A role says what kind of work a user may do. A current relationship says
> where they may do it. The caller supplies the exact persisted record lineage,
> and authorization checks the role and relationship together.

The module exists to centralize only recurring security behavior:

- authoritative current actor facts;
- self, assigned-Lab, hospital, project-Lab, project-wide, and Admin scope;
- exact project-role containment;
- equivalent SQL predicates for authorized lists;
- cross-cutting privilege-escalation safeguards;
- fail-closed composition through `require_any` and `require_all`.

It deliberately does not centralize route catalogues, action strings, disease
rules, camera/area/mydriatic validation, upload payload semantics, grading
workflow rules, referral logic, or other feature behavior.

## Mental model

There are two separate authorization worlds.

### Classical records

A classical record has no project and is located through its Lab Unit and
hospital. An accepted access path may combine:

- a permitted global work role plus direct Lab Unit assignment;
- a hospital-management role plus the actor's hospital;
- explicit Admin authority, but only where the caller intentionally permits it.

### Project records

A project record must carry a project ID and, for Lab-bound data, a configured
active Project-Lab Unit. Access requires an active `ProjectRoleGrant` for the
same project and a scope that contains the record:

- project-wide grant; or
- the exact Lab Unit grant.

A global classical role alone does not authorize project data. A project role
alone does not authorize classical data. Project-wide breadth must be explicit.

## What the core owns

### `AccessContext`

`authz.context.access_context(db, user)` captures current server-side facts:

- user ID and active status;
- current explicit global roles;
- actor hospital;
- directly assigned Lab Unit IDs;
- a request-local dictionary for repeated derived lookups.

The dictionary is not Redis and does not survive the request. Call
`clear_access_context()` after mutating authorization relationships.

### `RecordScope`

The caller represents one persisted target as exactly one of:

- `RecordScope.self(user_id)`;
- `RecordScope.classical(lab_unit_id=..., hospital_id=...)`;
- `RecordScope.project(project_id=..., lab_unit_id=..., hospital_id=...)`;
- `RecordScope.global_resource()`.

Do not guess the world or accept lineage solely from form/query/body fields.
Load the target and derive lineage from persisted parents. If required lineage
cannot be resolved, deny.

### Named scope helpers

- `self_scope`
- `assigned_lab_scope`
- `hospital_scope`
- `project_scope`
- `project_wide_scope`
- `admin_scope`
- `upload_scope`
- `grading_scope`
- `require_any` for alternative complete access paths
- `require_all` for independent authorities that must all be present

Role and scope must remain in the same branch. Do not separately check “has
some role” and “has some scope” and then combine unrelated evidence.

### SQL row helpers

`RecordColumns` and helpers in `authz.rows` reproduce the same access paths in
SQL. Incomplete column lineage evaluates to `false`, not broad access.

Lists must authorize in the query. Loading broad patient/image/task rows and
filtering them in Python or templates is forbidden.

## What domain access modules own

The core delegates exact workflow relationships to deep feature modules:

- `upload_profiles/access.py`: active uploader qualification, upload-profile
  assignment, configured Project-Lab Unit, active profile/binding;
- `tasks/access.py`: persisted task-to-project/Lab/hospital lineage;
- `grading/access.py`: current grading slot, project allocation, task
  participation, and inter-rater grade visibility;
- `services/uploads/access.py`: upload-record lineage and ownership;
- project, review, media, dataset, and inference services: their exact resource
  and state relationships.

These modules provide authorization evidence. They do not move the entire
domain workflow into `authz`.

## Contract for a single-record route

Every data-bearing route should follow this sequence:

1. **Authenticate.** Use the normal session/token boundary or an explicitly
   marked exact credential route. A public URL prefix is not authorization.
2. **Open the project-managed DB session.** Do not create an ad-hoc session.
3. **Parse transport input.** Validate types and required identifiers. Apply
   CSRF independently for forms/AJAX/HTMX mutations.
4. **Load the exact persisted target.** Resolve owner, project, Lab Unit,
   hospital, and parent lineage from the database. Body-supplied IDs are claims,
   not authority.
5. **Build the current actor context.** Use the live user and database session.
6. **Select the explicit behavior.** State which roles are accepted at each
   scope. Do not ask a hidden route catalogue.
7. **Authorize complete paths.** Use `require_any(...)` for alternatives or
   `require_all(...)` when all independent authorities are required.
8. **Run domain validation.** Validate workflow state, kind, disease, camera,
   area, mydriatic state, grading constraints, etc. in the owning service.
9. **Read or mutate narrowly.** For a mutation, authorize the current target
   immediately before changing it; lock/reload when concurrency matters.
10. **Return a deliberate disclosure response.** Follow the route family's
    established `403` or non-disclosing `404` behavior.

If any fact required by the selected behavior is missing, the route denies. It
must not silently fall back to a broader role or another authorization world.

## Contract for list and picker routes

1. Identify the same role/scope alternatives used by the record-detail route.
2. Provide complete `RecordColumns`, including `project_id` unless the model is
   explicitly `classical_only=True`.
3. Apply `role_scoped_rows`, a named behavior such as `clinical_rows`, or the
   domain's exact SQL clause before materialization.
4. Scope hospital/Lab/project picker choices too; unauthorized choices must not
   be offered and rejected only after submission.
5. Test parity: every returned row must pass the equivalent single-record
   decision, and every permitted representative record must be reachable.

## Contract for mutations and project-role administration

- Reload current actor, target user, existing grant, project, and requested
  scope from persisted state.
- Missing actor/target/scope facts deny.
- Non-admin self-grants deny.
- Only Admin appoints `PROJECT_PI` or `SITE_PI`.
- A PI may appoint `PROJECT_ADMIN` only inside the PI's own exact scope.
- A Project Admin may delegate operational roles only inside their own scope.
- A Lab-scoped delegator cannot create a project-wide or different-Lab grant.
- Clear request-local authorization context after a successful relationship
  mutation.

These ceilings belong in `authz/privilege_escalation_mitigation.py`. Project
workflow and UI rules remain in project services/routes.

## Contract for uploads

Authorization establishes only that the active user:

- holds the uploader qualification; and
- has one exact active upload-profile assignment for the target project/Lab and
  upload workflow.

The upload domain then validates the selected kind and all finer information.
An assignment does not imply project browsing, grading, analytics, review, or
inventory-management access.

## Contract for tasks, grades, and inter-rater views

- Resolve task lineage through persisted task/project/Lab/hospital parents.
- Classical grading requires current ophthalmologist qualification and the exact
  active disease/Lab/grading-slot relationship.
- Project grading additionally requires the exact active project allocation and
  target type/capacity.
- Admin and project-management roles do not bypass clinical eligibility.
- Inter-rater listing may reveal all grades only on tasks in which the actor has
  a qualifying grade and remains currently eligible. Unrelated tasks reveal
  nothing.

## Contract for workers and delayed downloads

- Store actor/credential identifiers and exact selected resource IDs in the job.
- Treat payload facts as hints, never authority.
- At execution, reload the active actor or share credential and every current
  resource/relationship/state fact.
- Require the persisted selected set to match the reauthorized set exactly.
- Revocation, deactivation, deleted lineage, foreign IDs, or incomplete facts
  deny the job rather than partially widening it.
- Download endpoints reauthorize the current owner/credential and the exact
  stored authorized row set.

## Route review checklist

A route conforms only if every answer below is explicit:

- Who is the authenticated actor or credential?
- What exact record(s) will be read or changed?
- Is each record classical, project-owned, self-owned, or global?
- Where did project/Lab/hospital/owner lineage come from?
- Which role is accepted at each scope?
- Is project-wide access intentionally required or merely convenient?
- Are upload, grading, allocation, participation, or other domain relationships
  required?
- What happens when any required fact is absent?
- Does the list SQL match the record decision?
- Is domain validation still in the domain service?
- Does a worker reauthorize current facts?
- Could Redis, a job payload, a request parameter, or a broad Admin check become
  the final authority? If yes, the route does not conform.

## Testing expectations for each route family

At minimum cover:

- anonymous/inactive actor denial;
- correct role but wrong Lab/hospital/project denial;
- correct scope but wrong role denial;
- missing lineage denial;
- cross-site and cross-project denial;
- inactive/revoked grant or assignment denial;
- exact allowed path;
- project-wide versus Lab-scoped distinction;
- record/list parity;
- mutation recheck;
- worker revocation where applicable;
- no domain-rule duplication inside `authz`.
