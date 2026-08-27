---
title: Authorization Rules
kind: policy
authority: self
status: authoritative — the single source of truth for authorization policy
related:
  - docs/10-DEVELOP/authorizations_rebac_engine.md
last_reviewed: 2026-08-26
---

# Authorization Rules

This document is the human-readable source of truth for authorization behavior.
Engine policies, route wiring, tests, and reviews must refer back to these rules.

Do not wire a route to an authorization action until this document has a rule for that action.

When code and this document disagree, stop and update the policy before changing enforcement.

## Global Rules

- Roles say what kind of work a user may do.
- Relationships say where the user may do that work.
- Upload access is granted by an upload profile assignment. Holding `admin`, `local_admin`, `data_manager`, or hospital scope is not itself upload access.
- `admin` reaches ingestion as break-glass through `ADMIN_GLOBAL`, without an uploader role or personal assignment. That is the exception path, not a second ordinary one. It replaces the ordinary actor authority but waives none of the selected profile's validation: the profile must still be active and configured for the target project, Lab Unit, upload kind and clinical dimensions; the created records must still carry the authorized project; and because this exception *writes* patient records rather than reading them, the decision must be recorded.
- Project is part of upload authorization: the selected upload profile must allow the selected project, and accepted uploads must tag created images with that project.
- Project is an active authorization boundary for patient media. Other domains
  remain on their documented classical or staged project-scoping rules until
  they are migrated explicitly.
- Grading access is granted by grading slots, not by lab-unit scope alone.
- A project grant's scope must match the breadth of the action's effect. Where the effect is confined to the rows touched, the scope filters rows and the narrowest grant qualifies. Where the effect spans the project, only a project-wide grant qualifies.
- The hospitals and lab units a project grant may name are derived from the project's configured lab units; a grant can never reach a lab the project does not use.
- Grading of project-owned tasks is governed by grader allocation, not by project role grants.
- General scoped access is granted by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Local-admin hospital scope applies only inside the user's hospital.
- System administration is reserved to `admin`. `user_manager` reaches only the explicit user-management actions, within its own hospital; `local_admin` and `data_manager` are not administration-console roles.
- Background workers are execution subjects, not users. They receive no human roles or interactive scope and may execute only work admitted by an authorized service boundary or an active stored automation rule.
- Break-glass reaches every action, including ingestion. Uploading by profile assignment is the ordinary path, not a rule that excludes `admin`.
- Two classes are outside it, and both are deliberate. An action scoped to the actor's own record - a password, a session, a notification, a viewer preference - is never reachable by break-glass: an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person. And a grading submission requires the grading slot itself, because the `admin` role does not stand in for the clinician role; an administrator who should grade holds a slot.
- An action outside those two classes that does not accept admin-global scope is a defect, not an exception.
- A route must load or derive the resource needed by the action before enforcing a resource-specific rule.

## Terminology

This system is relationship-based access control. Terms below follow the
standard ReBAC vocabulary; where a term is domain-specific, its standard
equivalent is named. Definitions are used in this sense throughout and in no
other.

**References.** Zanzibar (Pang et al., *Zanzibar: Google's Consistent, Global
Authorization System*, USENIX ATC 2019) for tuples, check and expand; Fong,
*Relationship-Based Access Control* (CODASPY 2011) for the model; OpenFGA for
`check` / `list-objects` and conditions; ISO/IEC 10181-3 for the separation of
decision from enforcement; ISO 22600 for privilege management over health data;
ANSI/INCITS 359 (RBAC) for role and constraint.

| Term | Meaning | Standard equivalent |
|---|---|---|
| **relation tuple** | The unit of authorization data: an object, a relation, and a subject. A project role grant is a tuple. | Zanzibar tuple `object#relation@user` |
| **relation** | The named link a tuple asserts - what this document calls a role held on a project or Lab Unit. | Zanzibar relation |
| **object** | What the relation is *on*. A project-wide grant is a tuple on the project; a lab-unit grant is a tuple on that Lab Unit. **Scope is the object, not an attribute of the grant.** | Zanzibar object |
| **subject** | The user, or a set of users, the tuple points at. | Zanzibar user / userset |
| **object hierarchy** | A Lab Unit belongs to a project, so a tuple on the project can reach it - but only because the model says so. Parent tuples do not propagate on their own: the relation must be rewritten through the parent (OpenFGA `define reader: reader from parent`). This is how a project-wide grant covers every Lab Unit without naming them. | Zanzibar tuple-to-userset; OpenFGA parent-child |
| **check** | The authorization decision: may this subject perform this action on this object? Answers permit or deny. | Zanzibar `Check`; ISO/IEC 10181-3 decision function |
| **list-objects** | Given a subject and an action, which objects may they reach. A relationship query in its own right, answering an authorization question about a set rather than a single object. It may be asked directly and does not presuppose a `check`. | OpenFGA `ListObjects` |
| **condition** | A requirement beyond holding the relation - for example an action whose effect spans a project, which a Lab Unit tuple cannot satisfy however many are held. Expressed here by *which object* the tuple must sit on, not by an OpenFGA condition: those are contextual predicates attached to a tuple and are not a substitute for object and relation structure. | XACML condition; NIST RBAC constraint |
| **delegation constraint** | A subject may create tuples only on objects its own tuples already reach, and never on a broader object. | ISO 22600 delegation; ARBAC administrative scope |
| **action** | The unit this document writes rules about. Resolved through relations rather than granted directly. | XACML operation; OpenFGA permission |
| **designation** | Who someone *is* on a project - principal investigator, co-investigator. Carries no relation and confers nothing. | — |
| **slot** | A position in the grading workflow: `resident`, `resident2`, `arbitrator`. Never a role, never in the role catalogue. | domain term |
| **assignment** | The tuple binding a user to an upload profile at a Lab Unit. Carries *where*; the profile carries *what*. | Zanzibar tuple |
| **break-glass** | `admin` reaching an action it holds no relation for, through a modelled `ADMIN_GLOBAL` relation rather than a branch taken before the engine. Reaches every action except the two classes below. | ISO 22600 |
| **separation of function** | Two parts of a workflow deliberately requiring different relations - assembling a dataset versus releasing it, uploading versus verifying. This is *not* separation of duty in the NIST sense: SoD constrains privileges so that one user cannot complete a sensitive operation alone, and here one person may hold both roles. The control is that each action names the relation it needs, so a holder of one cannot reach past it. | ANSI/INCITS 359 (RBAC), by contrast |
| **need-to-know** | Patient identifiers reach only the steps that must act on them. | ISO 22600; ISO/IEC 27002 |
| **least privilege** | Unused scopes are retired and no relation confers more than its object. | ISO/IEC 27002 |

Two consequences worth stating, because most of the divergence register follows
from them.

**Scope is the object of the tuple.** A grant does not "have" a scope that a
reader may consult or ignore; it *is* a tuple on a particular object. A
project-wide grant reaches a Lab Unit through the object hierarchy, and a
lab-unit grant reaches nothing above it. Treating scope as an attribute is what
allows a query to drop it - which is exactly divergence D-1.

**Check and list-objects ask the same question about different subjects of
enquiry** - one object, or a set of them. **Both are authorization decisions
and both fail closed.** A list endpoint that returns only the objects a
subject may reach has authorized every row it returned; a bug that widens that
set is a disclosure exactly as a wrong `check` would be.

The opposite reading is tempting and wrong: pass one coarse `check` at the
door, then treat row narrowing as ordinary query logic nobody needs to review.
Narrowing is not presentation. For a list endpoint it *is* the authorization,
and it is the part most easily got wrong quietly, because a query returning
too much still returns a plausible page.

## Roles And Designations

A **role** grants capability. A **designation** records who someone is on a
project - principal investigator, co-investigator - and grants nothing on its
own. Designations live on `project_investigators`; capability always comes
from a project role grant. `principal_investigator` and `co_investigator` are
therefore not in the role catalogue, and no policy may name one.

Designations are not inert. Being a principal or co-investigator carries
read-only oversight of the project: its analytics and grading statistics,
the uploads and EncounterSets, the project's own setup, who is configured on
it and which grading scheme it uses. Their grants carry `project_pi` and
`collaborator` respectively. Oversight observes and does not act: it grades
nothing, verifies nothing and adjudicates nothing.

`collaborator` is the non-PII browser role for international collaborators.
It browses a project's EncounterSets and views images without patient
identifiers. It does not ingest data, and it does not read identifiers off
an image: OCR'd text is still an identifier, so the OCR actions exclude both
`collaborator` and `analytics_viewer`.

### Grant scope

A project role grant carries exactly one scope: **`project`**, meaning the
whole project across every Lab Unit configured for it, or **`lab_unit`**,
meaning one such Lab Unit. Hospital scope **on a project role grant** is retired: reject it on write
and treat it as absent on read. This says nothing about classical hospital
scope, which `local_admin` still uses outside any project.

A grant's scope is authoritative. No role is promoted to a scope broader than
the one stored on its grant.

Two governance roles additionally constrain which scopes they may be granted
at, and the constraint belongs to the role rather than to any action:

- `project_pi` is granted at project scope only.
- `site_pi` is granted at lab-unit scope only. It may hold several Lab Units
  within a project - a site is not always one Lab Unit - but it may never
  hold the project itself. Because it is lab-unit-scoped, the project's site
  settings apply to it: it reads and exports its site's own encounters and data
  regardless, and reaches its graders' readings only where the project has
  enabled site grade export and it holds `data_exporter`.

This is why `site_pi` remains a distinct role although its action set matches
`project_pi`'s exactly. The name carries an invariant the scope column cannot
enforce on its own: a `project_pi` grant could be created at lab-unit scope by
mistake and nothing would object, whereas a `site_pi` grant at project scope
is invalid by definition and must be rejected on write. Naming the site role
separately also keeps the grants UI legible to whoever assigns it.

Every action is first a `check`: the actor either reaches it or does not.
Scope bears on that decision in one of two ways.

- **No condition** - the relation alone decides. A tuple on the project or on
  a Lab Unit both permit the action; the object the tuple sits on then
  determines which rows `list-objects` returns. Most read and clinical actions
  are of this kind, and the narrowing is enforcement rather than a second
  decision.
- **Project-object condition** - the action's effect spans the project, so
  only a tuple on the project itself satisfies it. Tuples on Lab Units do not,
  however many are held. Dataset curation is the clearest case: a dataset drawn
  from part of a project is not a smaller project dataset, it is not one.

A grant broader than an action's minimum always qualifies.

A third condition applies to the actions that confer authority on someone
else:

- **Delegation constraint** - the actor may create tuples only on objects its
  own tuples already reach, never on a broader one. A subject related to one
  Lab Unit writes tuples on that Lab Unit and nowhere else.

The delegation constraint is what lets access management be centralised or decentralised to
suit the project. A small project keeps one project-wide access manager; a
large multi-site one appoints an access manager per site, each administering
their own Lab Unit. The rule is the same in both cases, so the choice is
organisational rather than a change in policy.

This is why the manage actions carry a delegation constraint while dataset
curation and release carry a project-object condition, though both concern a
project's whole scope. The test is whether the action's effect can carry a
scope of its own. A grant can: it
records the Lab Unit it applies to, so partial authority produces a correct,
smaller result. A dataset cannot: one drawn from part of a project still
presents itself as the project's dataset, so the partial result is not merely
smaller but wrong.

### Governance and operational roles

**Governance** roles govern the project - who is on it, and oversight of what
it produces. Only a System Admin may grant one; no access manager may
delegate governance at any scope. `project_pi` is project-scoped, `site_pi`
lab-unit-scoped, `project_admin` either. Oversight observes and does not act:
it grades nothing, verifies nothing, adjudicates nothing, and ingests
nothing.

**Operational** roles do the project's work and may be delegated by a
`project_admin` within its own scope. Each is a filter over the rows its
grant covers.

### Admin scope and route defaults

Rules carried over from `admin_access_policy.md` and `RBAC_ABAC_Route_Policy.md`
when those documents were retired. They describe classical admin scope and are
unaffected by the retirement of hospital scope on project grants.

- `admin` has cross-hospital reach; `local_admin` administers one hospital and
  the Lab Units within it. Holding both needs no precedence rule: relations are
  disjunctive, so the engine evaluates each and permits if either admits. A
  tie-break is only needed where an implementation tests roles in sequence, and
  none should.
- An admin screen must not hide cross-hospital data merely because the account
  also carries a hospital assignment. Where a page offers a hospital or
  Lab Unit selector, the selector reflects the user's actual scope.
- `local_admin` is a first-class authorization relation, not a label. The
  hospital it administers is the object the relation sits on, exactly as a
  project grant sits on a project or a Lab Unit.
- A `local_admin` may administer more than one hospital. It holds one relation
  per hospital, and reaches exactly those. This is why the hospital cannot stay
  a column on the user record: a column holds one value, and the relation is
  what allows several.
- `current_user.hospital_id` is never an authorization rule. It is a column on
  the user record, so it is single-valued, unauditable, and invisible to the
  engine: nothing records *that* a user administers a hospital, only which one
  the row happens to name. A decision comparing it to a resource's hospital is
  a decision the engine never made and never logged.
- Every hospital-scoped decision goes through the engine, which resolves the
  relation and records the evidence that admitted it.
- Every route under `/admin/*` defaults to `admin` unless this document
  explicitly delegates it to another role.
- Each authorization migration compares this document's action inventory
  against the live URL map. A route absent from the inventory is unreviewed,
  not exempt.

**Every rule says whether break-glass reaches its action.** `admin` holding
everything is a claim about the model, not about any particular action, and a
reader deciding one endpoint should not have to hold the whole model in mind
to know whether an administrator can reach it. So a rule states it either way:
`admin` is break-glass here as everywhere else, or `admin` is not break-glass
here and the rule says why.

Which of the two a rule must say is not a matter of taste, and is not read off
the rule. It follows from the global rules above: break-glass reaches every
action except an action scoped to the actor's own record and a grading
submission. So the ten personal actions deny it, and every other authenticated
action affirms it explicitly. Merely naming `admin` among roles is not enough:
break-glass means authority through `ADMIN_GLOBAL`, while an administrator may
also act through an ordinary relationship such as a grading slot.

Only the seven deliberately public actions are silent, because an action that
requires no authentication has no authority to describe. They are not "open to
any authenticated user": that would describe the personal actions, which are
open to exactly one user each.

Stating the position makes the disagreements visible instead of inferable.
Three ingestion actions affirm break-glass while the code withholds it (D-39,
D-43); `grading.grades.view` affirms it while `admin` sits in its role set with
no grant source to match (D-32). Separately, the three grading submissions deny
break-glass because they require a slot, while D-50 records the different
question of whether `admin` is a valid grader role. Each disagreement is visible
precisely because the rule commits to a position.

### Reserved to a System Admin

Project setup carries consequences across the whole project and is never
delegable to `project_pi`, `site_pi`, or `project_admin` at any scope:
upload profile definitions, grading schemes and grading profiles, WAI autorun
configuration, Remidio API routing and connection bindings, and which Lab
Units a project spans.

### Every role states its purpose

A role exists only if its purpose can be written in one sentence that no
other role's sentence already covers. Two roles that authorize the same set
of actions are one role recorded twice; the difference people reach for is
almost always a *scope* or a *context*, and the grant already carries both.
This table is the catalogue, and `tests/unit/authz/test_role_catalogue.py`
asserts that every role in `auth.roles.DEFAULT_ROLES` appears here.

| Role | Purpose |
|---|---|
| `admin` | System administrator. Cross-hospital reach, break-glass on every action, and sole owner of the project setup that is never delegable: upload profile definitions, grading schemes, WAI autoruns, Remidio routing, and which Lab Units a project spans. |
| `user_manager` | Manages ordinary user accounts, classical roles, Lab Unit assignments, grading slots, enrolled devices and sessions within one hospital. Cannot manage or grant `admin` or `user_manager`, project grants, project grader allocations, or system configuration. |
| `local_admin` | Hospital-scoped operational role in the classical, non-project model. Distinct from both `admin` and `user_manager`: it reaches ordinary hospital work but no system or user administration action. |
| `fileUploader` | Ingests data. Classically it may create any kind of upload — direct, pre-graded or Remidio ZIP — but only into the Lab Units assigned to it. Inside a project the upload profile decides the kind and the upload grant decides the Lab Unit. The role alone authorizes nothing anywhere, and it does not verify. |
| `pregarded_uploader` | Ingests pre-graded image sets. The work is technical: identifying the AI model whose grades these are, and mapping the source sheet's values onto the standard grade catalogue. It asserts findings rather than only capturing images, and the generic uploading role does not confer it. |
| `optometrist` | Clinic-based clinician: uploads, and runs WAI inference. Does not verify. |
| `ophthalmologist` | The user-level qualification to grade. It authorizes no slot by itself: an active grading slot determines which workflow position the clinician may fill, and project work additionally requires a matching project allocation. All applicable relationships must hold. |
| `verifier` | Verifies uploaded data before it becomes gradable work. |
| `data_manager` | Administers the work without performing it: creates and reassigns regrade tasks and intra-rater batches, and allocates already-qualified graders within its project grant scope. |
| `discrepancy_reviewer` | Reviews cases where graders disagreed and records the reconciled reading. Does not adjudicate regrades. |
| `regrade_adjudicator` | Adjudicates a regrade. Cannot create the regrade work it adjudicates. |
| `dataset_creator` | Assembles datasets: curates, updates, finalises and deletes them. Reads and corrects identifiers burnt into images so they do not leave the system, and never reads record identifiers. Does not release. |
| `pii_exporter` | Operational. Releases data bearing patient identifiers. Every other role that may read an identifier may only read it in place; this one lets it leave the system. Held alongside the role that authorizes the release itself, never instead of it. |
| `data_exporter` | Releases datasets: exports them and administers shares. Only a finalised dataset may be released, and release carries project-wide scope. |
| `analytics_viewer` | Reads analytics and KPI statistics without patient identifiers. |
| `collaborator` | The non-PII browser for international collaborators. Browses; never ingests. |
| `project_pi` | The project's principal investigator: project-wide, read-only oversight of how the project is going. |
| `site_pi` | The principal investigator at one site: oversight of the Lab Units granted to them. May hold several Lab Units in a project; may never hold the project. Being lab-unit-scoped, its access to the project's site-gated work follows the project's settings - it exports its site's encounters and data freely, and its graders' readings only where the project permits and it holds `data_exporter`. |
| `project_admin` | The project's access manager. Delegates operational roles, uploader assignments and grader allocations within its own grant scope; a project-wide holder may also switch project-wide allocation enforcement. |
| `field_optometrist` | Field staff operating cameras away from the clinic. Distinct from the clinic roles because a stricter device and session policy applies. |
| `field_ophthalmologist` | Field staff operating cameras away from the clinic, carrying the ophthalmologist's clinical qualification rather than the optometrist's. Subject to the same stricter device and session policy. |

### Pre-graded ingestion is its own role

A pre-graded upload carries grades in with the images, so it asserts clinical
findings rather than only capturing data. The work is also technical in a way
capture is not: the uploader identifies the AI model whose grades these are -
which becomes a grader identity in its own right - and supplies the mapping
from the source sheet's values onto the standard grade catalogue. A wrong
mapping silently mis-grades everything it touches.

That is different work from a direct or Remidio capture, and
`pregarded_uploader` is the role for it. Note the contrast with the rule
above: a capture uploader may be a non-technical operator, which is why
verification is separated from uploading. Pre-graded ingestion is the
exception - it is an uploading role that requires technical judgement, and it
is a distinct role for that reason rather than a variant of the generic one.

`fileUploader` does not confer it. This holds in both contexts: classically,
and inside a project, where an upload profile may enable the pre-graded kind
but the holder must still be a `pregarded_uploader` rather than a generic
uploader.

The two bounds apply as they do for every upload - the profile decides the
kind is permitted, the grant decides the Lab Unit - and the role decides that
this particular kind of ingestion is the holder's work at all.

### Running inference at capture is not re-running it later

Inference at capture belongs to the step that captures: `optometrist`,
`verifier` and the field roles run it on data they are taking, as part of
taking it.

Re-running inference over data already captured is administration, not
capture. It is a batch decision about a project's existing records - which
workflows to apply, to what, and when - and it belongs to `data_manager`,
with `admin` as break-glass. No capture role confers it, and holding the
capture run does not confer the retrospective one.

This is the same separation as creating regrade work versus adjudicating it:
`data_manager` administers the work, and the clinical roles perform it.
`inference.wai.retry` already follows this rule.

### A project decides what each of its sites may do

Three settings govern whether a site - a lab-unit-scoped holder - may perform
work whose result represents the project as a whole. They are set **per Lab
Unit within a project**, on the binding between the two, so a study may trust
one site with work it withholds from another:

| Setting | Governs |
|---|---|
| `sites_can_export_grades` | Export of grades made by human graders, including the XLSX paths |
| `sites_can_create_datasets` | Dataset curation and finalisation |
| `sites_can_share_datasets` | Dataset sharing and release |

A site always exports its own encounters, images and captured data - that is
its own work and no setting withholds it. What is withheld by default is the
**grades**: the readings human graders produced on that data. Those are the
project's clinical output rather than the site's record of what it captured,
and a site takes them out only when `sites_can_export_grades` is on **and** the
holder has `data_exporter`. Neither alone suffices.

Each defaults to off, for each Lab Unit. The settings attach to the Lab Unit
within the project, so they govern **every lab-unit-scoped holder there** -
operational roles and `site_pi` alike - and the same person holding grants at
two Lab Units may export grades at one and not the other. Each withholds one
specific thing and nothing else: a setting that is off does not narrow a site's
access to its own data, only to the work named in the table. A project-wide
holder is unaffected by any of them.

The natural home is the project-to-Lab-Unit binding, `ProjectLabUnit`, which
already carries the `active` flag for that pair. A setting on the project alone
could not express a study that trusts one site and not another; a setting on
the Lab Unit alone could not express a Lab Unit that serves two projects under
different terms.

These settings are what make the project-object condition a decision rather
than a law. Curation and release are project-wide by default because a dataset
drawn from part of a project does not represent the project - but whether that
matters is the project's call. A multi-site study may want each site curating
and exporting its own arm; a pooled study may not. The default answers the
question conservatively; the setting answers it deliberately.

They constrain and never confer. Turning one on does not grant anyone
anything: it removes a restriction on holders who already have the role at
lab-unit scope. Turning one off withdraws the work from every site at once,
which is why it belongs to the project rather than to each grant.

### Ingestion and verification are different work

Uploading has three generations layered on top of each other, and the role
names still carry the archaeology. Classically there were three uploaders -
ZIP, direct and pre-graded. The project era added EncounterSets and API
ingestion through upload profiles while keeping all three classical
mechanisms. A mobile surface for field staff is arriving on top of that.
`fileUploader` is the merged classical uploader; `pregarded_uploader` is
what the merge left behind.

Verification is deliberately **not** part of that lineage. An uploader may be
a non-technical operator; deciding whether captured data is fit to become
gradable work needs someone technical. `verifier` exists for that judgement
and was moved off `optometrist` for the same reason.

**`verifier` is the only role that authorizes verification**, with `admin` as
break-glass. Not `fileUploader`, not `data_manager`, not `local_admin` - each
held it by inheritance rather than by decision, and every additional holder
is ambiguity about who is accountable for the judgement. A user who should
verify is granted `verifier`.

### Assembling a dataset and releasing it are different work

`dataset_creator` assembles: it curates, updates, finalises and deletes.
`data_exporter` releases: it exports and administers shares. Neither does the
other's job, and `dataset_creator` holds no release action at all.

The cut is egress. Assembling a dataset keeps patient data inside the system;
exporting a file or minting a share link takes it out, which is a different
risk and belongs to a different holder - the same reasoning that separated
verification from uploading and adjudication from creating the work.

Release carries the project's whole scope, exactly as curation does: a
release may draw on part of a project's data or all of it, so a lab-unit
grant confers nothing. And only a curated, finalised dataset may be released
at all.

Separating the work does not separate the people: one person may hold both
roles. The control is that each action names the role it needs, so a holder
of only one cannot reach past it - not that assembly and release must sit in
different hands.

`admin` remains break-glass throughout and holds both, as it does everywhere
else in this document.

### Uploading is bounded twice

An upload is authorized by two independent bounds, and both must hold. Neither
substitutes for the other, and holding the role is never sufficient on its own.

**What may be uploaded** - the kind: direct image, pre-graded set, Remidio ZIP,
EncounterSet package, Remidio API sync. Inside a project the upload profile
carries this, along with the clinical dimensions it constrains. Classically
there is no profile, so all kinds are permitted.

**Where it may be uploaded** - the Lab Unit. Classically this is the
uploader's explicit lab-unit assignment. Inside a project it is the scope
recorded on the upload grant when the user was assigned: one Lab Unit, or the
whole project.

An upload profile does not itself name a Lab Unit. The profile says what kind
of data and under what clinical constraints; the grant says where. A user
holding a profile with no grant covering the target Lab Unit may upload
nothing there.

So classical uploading is broad in kind and narrow in place: a `fileUploader`
may upload anything, but only into the Lab Units assigned to them. Project
uploading is narrow in both.

### Releasing identifiers is its own action

An export that carries patient identifiers out of the system is not the same
action as an export that does not, and the difference is modelled as two
actions rather than as one action masked differently per caller.

`f9e3ffa8` made disclosure a property of the action for a measured reason:
masking had been decided from the actor's roles, by the weakest of them, so
seven of twenty-one active users were unmasked everywhere including the
grading screen. Deciding it from the actor is the failure that produced that,
so it is not reintroduced here.

- The ordinary export action carries `shows_pii = false` and emits the record
  with identifiers masked. `patient_id` is masked, and so is `zip_filename`,
  which embeds the patient number in every row by naming convention and is
  therefore an identifier whatever its column name suggests.
- A distinct identifier-bearing action carries `shows_pii = true` and requires
  **`pii_exporter`** in addition to whatever role authorizes the export at all.

Both bounds must hold: `data_exporter` decides whether the actor may release,
`pii_exporter` decides whether identifiers are included in what is released.
Neither substitutes for the other, so a holder of one alone gets the masked
export or none.

`pii_exporter` is an operational role: a `project_admin` may delegate it
within their own scope, like any other. It follows the same scoping principle: it acts within its defined scope - the Lab Units assigned to it outside
a project, and the project or Lab Unit its grant names inside one. Scope
decides which records it reaches, never whether it may act.

That is separate from how broadly a release may draw. Whether an export spans
a whole project remains governed by the release action itself; `pii_exporter`
decides only whether identifiers are included in whatever that export covers.

### Throughput figures and clinical figures are different

An aggregate is not automatically ungated. What decides it is what the figure
is *about*.

**Throughput** - how many images a Lab Unit captured, how many uploads it
processed, how far its verification queue has moved - is a fact about that Lab
Unit's own work. Classical scope reaches it, and a project relationship is not
required.

**Clinical findings** - distributions of DR grades, glaucoma results, VCDR
values - are a project's results, whatever they are aggregated over. They are
project-gated exactly as the underlying records are, and a Lab Unit's own
throughput reasoning does not extend to them.

The record-list test decides *how much* an endpoint discloses; this decides
*whose data it is*. Both apply.

### Roles whose purpose does not distinguish them

These are recorded as debt, not as policy. Each states a purpose above that
another role's purpose already covers, so each is slated to collapse into a
scope, a context, or its parent role. Until they do, the duplicate-action
test in `test_role_catalogue.py` carries them on an explicit allowlist, so
the test still fails for any *new* duplicate.

| Role | Collapses into | Why |
|---|---|---|

`field_optometrist` and `field_ophthalmologist` authorize identical action
sets today, but that is a **gap rather than a duplicate**. In the clinic the
two professions differ sharply: `ophthalmologist` carries the grading
qualification and the grade views, `optometrist` carries capture, inference
and pre-processing. The field pair does not yet mirror that split, so a field
ophthalmologist cannot grade on the mobile surface where a clinic one can.
Resolve by giving the field roles the distinction their clinic counterparts
have - not by merging them. A `field_ophthalmologist` grades; a
`field_optometrist` captures.

Grading in the field is reached the same way as anywhere else, through a
grading slot. The surface does not change the rule: the clinical qualification
comes from the role, the step comes from the slot, and both must hold. Field
grading therefore needs slots allocated for it, and a field ophthalmologist
without one grades nothing.

`resident`, `principal_investigator`, `co_investigator` and `coordinator`
remain as rows in the `roles` table but are retired: they appear in no
policy and confer nothing. Anyone still holding one gains no authority from
it.

## Image Access Is Authorized On The Object

Images are authorized where the bytes are served, not where the page is
rendered. The grading workbench, the task viewer and the discrepancy review
viewer each render their own page under their own action, and all three then
fetch the image through the shared `encounter_viewer`, which authorizes
`media.image.view` against the image itself.

This is the right shape - a page gate cannot protect a resource fetched by a
later request - but it has a consequence worth stating plainly: **the page
actions do no security work for image bytes.** Narrowing the roles on a viewer
page does not narrow who can retrieve the images it shows. `media.image.view`
is the single control, and every rule about who may see an image belongs
there.

## Patient Identifiers

Three different things are called patient identifiers, and they are governed
separately.

**Record identifiers** are the patient's details held on the encounter -
name, address, and the rest. Reading them is disclosure and nothing else.
They belong to capture, upload and verification, which need to know which
patient an encounter is. Grading, discrepancy review, regrade adjudication,
intra-rater work, analytics, dataset curation and export never need them.

**Image identifiers** are details burnt into the image itself, found by OCR.
Seeing them is how they get removed. They belong to capture, upload,
**verification and dataset curation** - the steps that correct an image
before it moves on. A curator filters to the images OCR flagged, opens the
detections to see what and where, and corrects them; this is the same work a
verifier does at the verification step, and it is the last chance to catch a
leak before data leaves the system.

So dataset curation reads image identifiers and not record identifiers: it
needs to know an image carries a name in order to crop it out, and never
needs to know whose name it is.

**Embedded file identifiers** are the camera's own tags - EXIF and the like -
travelling inside the image file. They are patient identifiers and are treated
as such.

They differ from the other two in one way that makes the rule stricter, not
looser: **removing them does not require reading them.** Burnt-in text must be
inspected before it can be cropped, so the correcting steps must see it. EXIF
can be stripped without anyone looking at it, so no workflow step needs its
contents. Every ingestion path strips EXIF. Whether a stored image still carries any is
reported as a flag - `exif_present` - which discloses no patient detail but is
still confined to the roles that may read image identifiers: it says an image
is unclean, which is only actionable by whoever may clean it, and a
browse-only role has nothing to do with the answer.

The tags themselves are disclosure. They are readable only by the roles that
may read image identifiers, and only for diagnosing why a strip failed. A role
that browses without identifiers never receives them, whatever request
parameter it sets.

This is a property of the action, not of the actor's roles. Deciding it from
roles alone unmasks a grader who also happens to upload, on the grading
screen itself. An action that has not been classified masks by default.

## The Pipeline And Its Steps

Work moves through three steps, and each is scoped by a different
relationship. Holding one step confers nothing at the next.

**1. Upload.** An uploader sees the uploads in a lab unit, the progress of
the upload jobs there, and the status of the WAI and Remidio OCR inferences
those uploads trigger. Within a lab unit they see every upload, not only
their own; "mine" is a filter on that list rather than the boundary of it.

- Outside a project the reach is the uploader's own lab units.
- Inside a project it is the (project, lab unit) pairs covered by their
  upload profile assignments.
- An uploader is not a verifier. Upload access confers no verification and
  no grading authority.

**2. Verification.** A verifier confirms what was captured.

- Outside a project the reach is the verifier's own lab units.
- Inside a project it is the lab units assigned to that verifier within the
  project, held through an explicit project role grant carrying a
  verification role.

**3. Grading.** A grader reads the images clinically.

- Outside a project eligibility is the grading slot: role slot, lab unit and
  disease together, held on top of a grader role at user level.
- Inside a project the same slot applies and a project grader allocation is
  required as well.
- A grader reads their own grades, and every other grade on a task they
  graded, including the second reader's, the arbitrator's and the AI grade
  allocated to that task, so they can see how their readings compare. That
  visibility is bounded by participation: grades on tasks they did not grade
  stay out of reach.

**4. Discrepancy review and regrade adjudication.** Both work the same way:
the role, in the lab units allocated to the actor.

- Outside a project those are the actor's own lab units.
- Inside a project they are the lab units the project allocated to them,
  carried by a project role grant for the same role. Lab-unit assignment
  alone never reaches a project's data.
- Discrepancy review needs `discrepancy_reviewer`; regrade adjudication
  needs `regrade_adjudicator`.

**Browsing tasks and exporting data** follow the same rule as the review
stages: the role, in the lab units allocated to the actor outside a project,
and the scope the actor's project grant covers inside one - project-wide,
hospital or lab unit. Task browsing is what feeds regrade and intra-rater
creation, so it also accepts a project's governance roles, since a PI or
project admin must be able to see their own project's work.

**Creating the work is separate from doing it.** Regrade tasks and
intra-rater batches are created, and reassigned, by `data_manager` under the
same lab-unit rule. Adjudicating a regrade needs `regrade_adjudicator`, and
grading an intra-rater task needs a grading slot. Neither administrative
role can perform the clinical step, and neither clinical role can create the
work.

**Inference.** The WAI and Remidio OCR inference browser follows the upload
step it reports on: the actor's own lab units outside a project, and their
upload assignments inside one. Field staff follow the same rule, not an ownership rule:
`field_optometrist` and `field_ophthalmologist` reach the uploads and
inferences in the Lab Units their upload profile assignments cover. Ownership
is a filter offered over that set, never the condition for reaching it - an
automated Remidio pull is created by a schedule rather than a person, so it
carries no owning user, and gating on ownership would hide exactly the rows
field staff need. See `inference.wai.summary` for the full statement.

## Existing Policy Sources

These documents already contain authorization policy language and should be
checked before adding or changing a rule here:

- `docs/03-Tasks/Scoping.md`
- `docs/API/upload-profiles/README.md`
- `docs/API/mobile/context.md`
- `docs/API/core/direct-uploads.md`
- `docs/03-Tasks/reviewSystem.md`
- `docs/03-Tasks/Intra-rater-tasks.md`
- `docs/03-Tasks/comprehensive_task_management_system.md`
- `docs/03-Tasks/taskCreationServices.md`
- `docs/07-Datasets/Dataset_Share_Process.md`
- `docs/API/datasets/sharing-download.md`
- `docs/API/media/README.md`
- `docs/API/jobs/status.md`

Older route-policy and PII documents may contain useful policy statements, but
they also contain staged work and stale assumptions. Treat them as evidence, not
as the final source of truth, until their rules are copied into this document.

## Current Domain Rules To Preserve

These rules summarize behavior found in existing docs and code. They are not all
wired to `authz/policies.py` yet, but future wiring must preserve them or update
this document first.

### Uploads

- Rule: A user may view upload dashboards when the user has one of `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `optometrist`, or `fileUploader`; dashboard access does not imply upload form access.
- Rule: Uploading is authorized at two points and by the same engine at both. No role, `admin` included, short-circuits either.
- Rule: **Entry** - opening an upload form, calling an upload helper API, or reading an eligibility selector requires an uploading role and at least one active upload profile assignment. This asks whether the subject reaches *any* object for the action, so that a form is never rendered whose every option would be refused.
- Rule: **Mutation** - submitting an upload requires the same uploading role and an assignment covering *the selected Lab Unit and upload kind*, checked against the selection rather than against the project's configuration.
- Rule: Neither bound substitutes for the other at either point. A role with no assignment authorizes nothing; an assignment held by a subject with no uploading role authorizes nothing.
- Rule: `admin` reaches both points through its own modelled relation, evaluated by the engine like any other. Break-glass is a grant, never a branch taken before the engine runs.
- Rule: Break-glass ingestion relieves only the requirement that the actor hold an assignment. The profile selected must still be active and configured for the target, and the created records must still carry the authorized project. An administrator supplies the target explicitly; the assignment is what ordinarily supplies it, and break-glass does not supply one.
- Rule: Because break-glass ingestion creates patient records, the decision is recorded with the evidence that admitted it.
- Rule: A user may submit a direct, Remidio ZIP, pregraded, or encounter-set upload only when the selected upload profile is active, assigned to the user, and matches the selected project, lab unit, disease, camera, area, mydriatic state, and upload kind.
- Rule: Every accepted upload must persist the authorized project tag onto the created upload/image records so later migration to project-scoped access has a reliable data anchor.
- Rule: Direct-image duplicate detection is global by image content hash. A duplicate attempt must not create a new `DirectImageUpload`.
- Rule: A duplicate direct-image attempt must remain visible in the current upload job as a duplicate item that points to the canonical older `DirectImageUpload`.
- Rule: Duplicate direct-image attempts must not create `DirectImageVerify` rows, verification jobs, thumbnail jobs, metadata jobs, PII jobs, or user upload-count increments for the submitted duplicate bytes.
- Rule: Returning the canonical thumbnail, task, and AI result for duplicate content is allowed because the uploader submitted identical image bytes.
- Rule: AI result reuse for duplicate direct images is model-specific and must use only the Wadhwani model linked to the current upload profile. Human grades must never be copied or created by duplicate handling.
- Rule: Admin, local-admin, data-manager, and master-admin status do not create upload-profile access by themselves.
- Rule: Upload profile management is allowed for `admin`, `local_admin`, or `data_manager` only within the manager's allowed lab-unit scope.
- Rule: Selected uploaders for a profile must already be assigned to the profile lab unit.
- Rule: Mobile upload APIs require a valid mobile bearer session, an active user, the `fileUploader` role, and the same active upload-profile relationship used by web uploads.
- Rule: A manual Remidio API project sync requires an active upload-profile assignment whose kind permits Remidio API sync and whose Lab Unit scope covers every active route the requested project sync will use. Listing a project as eligible is not authorization to submit it.
- Rule: The user who started a manual Remidio API project-sync job may pause, resume or cancel it only while that same user still holds the project-sync authority; `admin` is break-glass. Another eligible uploader does not inherit control of the job.
- Rule: Scheduled Remidio API pulls have no requesting user. They are admitted only by the active stored prospective-sync, routing-profile, source-rule and project-binding configuration, and workers may process only the exact project and routes that configuration selected.
- Rule: Remidio connections, routing profiles, source rules and project bindings are system configuration and require `admin`; this is separate from permission to run a manual project sync.

### Verification

- Rule: Verification pages are hospital-bound and lab-unit-scoped unless a policy explicitly accepts admin-global or hospital-scope access.
- Rule: Direct-image verification and editing require one of `verifier` or `admin` plus access to the direct image's lab unit or hospital scope.
- Rule: Remidio encounter verification requires one of `verifier` or `admin` plus access to the encounter lab unit or hospital scope.
- Rule: Encounter-set verification requires `verifier`, or `admin` as break-glass, plus access to the encounter set - the same rule as direct-image and Remidio verification. No uploading, clinical or administrative role confers it.
- Rule: A verification mutation must not proceed if downstream task state makes unverification, editing, or retagging unsafe.
- Rule: Verification routes must resolve the encounter, report, direct image, or encounter-set image before enforcing object-specific access.

### Grading

- Rule: Grading follows active `UserDiseaseUnitRole` rows for the task disease and lab unit.
- Rule: Resident grading requires a compatible role and a grading-slot relationship with `can_grade_resident`.
- Rule: Resident2 grading requires a compatible role and a grading-slot relationship with `can_grade_resident2`.
- Rule: Arbitration requires a compatible role and a grading-slot relationship with `can_arbitrate`.
- Rule: Grading and arbitration may cross hospitals only through grading-slot relationships; lab-unit assignment alone is not enough.
- Rule: Grading routes must also enforce task state, role-slot order, and duplicate-grade prevention.
- Rule: `resident`, `resident2` and `arbitrator` are grading slot names, never user roles. Route gates and candidate queries must derive them from active slots rather than accepting same-named roles.

### Project Grader Allocation

- Rule: A project grader allocation is a workflow relationship binding an already-qualified user to one project, Lab Unit, active grading target and grading capacity. It is never a role and never a grading slot.
- Rule: `project.grader_allocations.view` permits `project_pi`, `site_pi`, `project_admin` and `data_manager` to read the allocation plan through an explicit project role grant. The grant's object limits the rows: a project grant sees the project; a Lab Unit grant sees that Lab Unit. `admin` is break-glass.
- Rule: `project.grader_allocations.manage` permits `project_admin` or `data_manager` to create, reactivate or deactivate allocations through an explicit project role grant, with `admin` as break-glass. Hospital scope, `local_admin`, and classical Lab Unit assignment alone never reach project allocations.
- Rule: Allocation management is contained. A project-scoped manager may allocate at any configured Lab Unit in the project; a Lab Unit-scoped manager may allocate only at that Lab Unit and cannot write a project-wide relationship.
- Rule: A manager may not allocate themselves. An allocation must be made by another actor holding the required management authority.
- Rule: Creation or reactivation requires an active target generated from the project's active upload and grading configuration, an active user holding `ophthalmologist`, and a compatible active grading slot for the selected Lab Unit, disease and capacity. `resident`, `resident2` and `arbitrator` remain slot names, not candidate roles.
- Rule: An allocation never substitutes for the clinical role or slot. Revoking the user, `ophthalmologist`, or the matching slot makes the allocation ineffective immediately but does not delete its history.
- Rule: `project.grader_allocation_policy.manage` permits only a project-scoped `project_admin` to enable or disable allocation enforcement for the whole project, with `admin` as break-glass. A Lab Unit-scoped `project_admin`, `data_manager`, `local_admin`, `project_pi` or `site_pi` cannot change this project-wide rule.
- Rule: Enforcement may be enabled only when every active grading target has effective reader coverage. Coverage counts only allocations whose user, clinical role and matching slot are all active. The server derives targets and candidates; client-supplied names, roles, target labels or scope claims are never authority.
- Rule: Allocation changes are activated or deactivated rather than deleted, and record actor, time, target, Lab Unit and capacity. They affect future task acquisition and submission checks, never the attribution or authority record of a completed grade.
- Relationship source: project role grant for management; project grader allocation for project grading; admin-global scope for break-glass.
- Resource: project and grading target; Lab Unit when scoped.

### Discrepancy Review And Regrade

- Rule: A user may view discrepancy review queues only when the user has a discrepancy-review role accepted by the route policy and the tasks are in the user's allowed lab-unit or review scope.
- Rule: A user may create or download the masked discrepancy review export only when the user has `data_exporter` or `data_manager` and the exported tasks are in scope; viewing or reviewing the queue does not confer release.
- Rule: A discrepancy export containing patient identifiers is the separate `review.discrepancy.export_pii` action and additionally requires `pii_exporter`. The additive permission never widens the tasks authorized by the base export action.
- Rule: A user may submit task review decisions only when the user is a discrepancy reviewer for the task workflow.
- Rule: Regrade task creation and reassignment require `data_manager`, or `admin` as break-glass, and must preserve lab-unit and task-state constraints. `local_admin` does not confer it: administering the work is `data_manager`'s, and performing it needs `regrade_adjudicator`.
- Rule: Review and regrade policy must distinguish read-only review visibility from mutation authority.

### Intra-Rater

- Rule: A user may create or administer intra-rater batches only when the user has `admin` or `data_manager` and the selected lab unit is in the user's allowed scope.
- Rule: A user may view assigned intra-rater tasks when the user is the assigned grader or has an administrative role accepted by the policy.
- Rule: A user may submit an intra-rater grade only for an assigned intra-rater task and only when the task state accepts submission.
- Rule: Intra-rater task creation must validate selected graders, disease, lab unit, and normal-grade configuration before creating tasks.

### Ad Hoc Tasks

- Rule: A user may create ad hoc grading tasks only when the user has `admin` or `data_manager` and every selected source image or task is within the user's allowed lab-unit scope.
- Rule: Ad hoc task creation must use verified or otherwise eligible source images according to the task-creation service rules.
- Rule: A user may view or delete an ad hoc batch only when at least one created task in the batch is within the user's allowed lab-unit scope.

### Analytics

- Rule: Public analytics and authenticated KPI analytics are separate authorization surfaces. Only the explicitly designated public analytics page and its aggregate APIs require no user relationship.
- Rule: Public analytics may return only approved system-wide totals, trends and aggregates. It must never return patient rows, identifiers, export files or project clinical-result drill-downs.
- Rule: A user may view authenticated KPI analytics only when the user has an analytics-capable role and the data is covered by admin-global scope, hospital scope, explicit lab-unit assignment, or the exact project relationship stated by the action.
- Rule: Analytics exports must apply the same scope as the corresponding analytics view.
- Rule: Analytics and exported outputs must preserve PII masking/anonymization requirements from the PII exposure policy.

### Datasets And Export

- Rule: A user may view dataset curation lists only when the user has a dataset/analytics-capable role and the candidate images are in scope.
- Rule: A user may create or update curated datasets only when the selected images are in the user's allowed scope.
- Rule: Dataset export requires `data_exporter` (or `admin`) and a finalised dataset. `dataset_creator` assembles and does not release.
- Rule: Dataset sharing is limited to `data_exporter` and `admin`. Sharing is release, not assembly, so `dataset_creator` does not confer it.
- Rule: Public dataset downloads require the exact active, unexpired share token, successful OTP verification, accepted terms, and the exact dataset named by the share. Session roles alone confer nothing and the credential reaches no other dataset.
- Rule: A public share cannot add identifiers to an export. Any share whose files contain patient identifiers requires `pii_exporter` in addition to the role that authorized release, before the files are made available.
- Rule: Dataset exports and shares must preserve anonymization and PII controls before files are made available.

### Admin And Local Admin

- Rule: `admin` has cross-hospital access only for actions whose policy accepts admin-global scope.
- Rule: System administration actions are `admin` only. Hospital, project, workflow and clinical roles do not confer administration-console access.
- Rule: `user_manager` may manage ordinary user records, roles, Lab Unit assignments, grading slots, enrolled devices and sessions inside its own hospital only. It may not manage or grant `admin` or `user_manager`, write project grants or project grader allocations, or change system configuration.
- Rule: `local_admin` has hospital-scope access to ordinary classical work inside the user's own hospital and must not cross hospitals. It confers no system or user administration action.
- Rule: A user may hold both `admin` and `local_admin`. Relations are disjunctive: each is evaluated and either may admit, so there is no precedence between them. `admin` reaches further only because more actions accept admin-global scope, not because it outranks anything.
- Rule: `master-admin` is not an authorization bypass for upload, grading, or route-level ReBAC policies.
- Rule: Admin routes that load hospital-scoped data must use shared scoping helpers and must not rely on `current_user.hospital_id` alone.
- Rule: Sensitive admin actions, database restore, security configuration, S3 configuration, system maintenance, and rate-limit administration require explicit admin-only policy unless a local-admin exception is written here.

### Jobs

- Rule: A user may view a job when the job was created by the user, the job belongs to an allowed lab unit, or the user's role and policy grant admin/hospital scope.
- Rule: A user may view job results or regenerate job artifacts only when the job is visible under the same owner or lab-unit rule and the action-specific role is accepted.
- Rule: Job APIs must not expose another user's job details unless the job's lab unit is within scope or a policy explicitly accepts broader access.
- Rule: A background worker receives no human role. A manual job carries its requester for attribution, not as delegated worker authority; a scheduled job is admitted by its active stored rule and exact target.
- Rule: An interactive retry, resume, cancellation or change is a new action and must be authorized before it is queued. A worker may not fabricate a user context to admit work that no user or automation rule authorized.

### Media

- Rule: A user may view media only when the referenced image, thumbnail, or PDF is covered by signed-token access, admin-global scope, hospital scope, or explicit lab-unit assignment.
- Rule: Project-linked media may also be covered by an exact scoped project role, legacy project capability, collaborator relationship, grading-task eligibility, or direct-upload ownership accepted by the action policy.
- Rule: Broad media route roles are not sufficient without object-level hospital or lab-unit validation.
- Rule: A direct uploader relationship is bound to the exact uploaded image UUID and does not grant project-wide media access.
- Rule: Legacy media paths, mobile upload thumbnails, and glaucoma-AI image delivery must all pass the shared media resolver before reading storage paths or bytes.
- Rule: Generated dataset, analytics, discrepancy-review, and EncounterSet export artifacts are authorized at their dataset/job/export service boundary. They are not raw UUID media routes and must retain their stricter owner and scope checks.
- Rule: Trusted ingestion, OCR execution, inference, thumbnail generation, and export workers operate only on work already admitted by an authorized service boundary; they must not fabricate an interactive user context.
- Rule: Authorization telemetry must not record cache-hit state, media UUIDs, source types, storage paths, denial reasons, tokens, or cache keys for denied requests.

### Search

- Rule: A user may search images, tasks, or encounters only when the search query is constrained to the user's allowed hospital or lab-unit scope.
- Rule: A user may view a search result detail only when the underlying task or image is in scope.
- Rule: Search results and audit exports must preserve masking expectations for sensitive fields.

### Preprocess And Anonymization

- Rule: A user may view preprocessing dashboards only when the user has an accepted preprocessing role and the images are in allowed hospital or lab-unit scope.
- Rule: A user may anonymize, restore, or override PII on an image only when the image is in allowed scope and the action's role is accepted.

### Screenings And Reports

- Rule: A user may view screening records or reports only when the underlying encounter or report is in allowed scope.
- Rule: A user may reprocess or delete screening records only when the user has a mutation-capable role and the encounter is in allowed scope.
- Rule: Report lookup by UUID must still enforce object scope before returning report data.

### API Lookups And Context

- Rule: Lookup APIs must require a logged-in session or valid token unless explicitly public.
- Rule: Lookup APIs that return hospitals, lab units, users, image metadata, OCR data, or viewer settings must filter results to the caller's allowed scope.
- Rule: Mobile context may expose role and lab-unit information from token claims, but uploads and mutations must still revalidate against server-side relationships.
- Rule: A field device may sign in only after a System Admin or the target user's hospital-scoped `user_manager` issues a one-time enrolment code and the server records the approved device relationship.
- Rule: `admin` or the target user's hospital-scoped `user_manager` may approve or block that user's device and revoke its mobile sessions through explicit user-administration actions. Blocking a device must invalidate its existing sessions; an old token is not continuing authority.
- Rule: A user may still list and revoke only their own mobile sessions through the self-scoped mobile actions; administrative device management never impersonates the user.

### Workflow State

- Rule: Authorization is evaluated against current resource and workflow state at mutation time, not inherited from a previously rendered page, eligibility list, queued request or stale token claim.
- Rule: Verification mutations stop when downstream grading state makes editing, unverification or retagging unsafe.
- Rule: Grading submissions require the currently valid task state, role-slot order, active slot and any required project allocation, and must prevent duplicate submission.
- Rule: Regrade, intra-rater and ad hoc task mutations must revalidate source eligibility, current assignment and state before changing work.

## Divergences To Reconcile

Where this document and the code disagree. The rule stands; the code is what
moves. Items are numbered so they can be cited from beads and commits.

Every entry was re-verified against the code on 2026-08-26. Nothing here may be treated as enforced. Registry parity proves that every
registered action has a policy, not that any route consults it (D-14).

### Scope and grant management

**D-1 — Governance promotion overrides stored scope.**
`data_authorization/policy.py` defines `PROJECT_WIDE_GOVERNANCE_ROLE_NAMES`
and short-circuits on it, so any active `project_pi` or `project_admin` grant
authorizes project-wide regardless of the scope stored on it. This makes
"a grant's scope is authoritative" false for the two roles that manage
access. `site_pi` is excluded and already behaves as this document
describes. Introduced in `2f701d88` with no stated rationale.

**D-2 — `project.access.manage` ignores scope entirely.**
`data_authorization/service.py::_require_manage_scope` checks that the actor
holds *some* active `project_admin` grant on the project. It reads neither
that grant's scope nor the scope being written, so a lab-unit-scoped access
manager can mint project-wide grants, including for themselves. Tracked as
`fundus_img_xtract-yc0j` (AUTHZ-03).

**D-3 — `_manageable_grant_clause` has the same gap on the read path.**
Any manager grant expands the visible set to every configured Lab Unit.

**D-4 — `project.uploaders.manage` has the same gap.**
`upload_profiles/admin_service.py` evaluates the action with no
`lab_unit_id`, then validates the requested Lab Units against project
configuration rather than the manager's own scope.

**D-5 — There are two policy engines, and the live one is the wrong one.**
`authz` decides authorization. `data_authorization` owns the persisted grant
representation and feeds it to `authz` - its own service docstring says it
"is not a second policy decision engine". `data_authorization/policy.py` is
precisely that: a parallel decision engine with its own action-to-role map,
its own scope logic, and its own promotion set.

The two are kept in step only by comments - `authz/policies.py:358` says it
"mirrors `data_authorization.policy` role groups so the two agree", and
`authz/predicates.py:563` says the same of scope resolution. They do not
agree, and nothing detects when they stop.

Most of the divergences in this register are symptoms of this one. D-22 is a
PII fix applied to `authz` while the live path kept reading the old rule.

On access management there are **three** answers, not two, and this document
is a fourth: this document permits lab-scoped administration under a delegation constraint;
`authz/policies.py` requires a project-wide grant (`min_scope=PROJECT_SCOPE`)
and would therefore *under*-authorize; the live service ignores scope entirely
and *over*-authorizes; and its read-side predicate expands any manager to
every configured Lab Unit. Consolidating onto `authz` as it stands would swap
one wrong answer for another, so D-2 and D-3 are not fixed merely by calling
the other engine — the rule itself must be written first.

**`authz` is the single authorization module.** `data_authorization` is
folded into it entirely - the grant ORM, grant management, DTOs and
exceptions become part of `authz`, and `data_authorization/policy.py` is
dissolved into `authz/policies.py` rather than moved.

Splitting authorization across two packages is what allowed the two to
disagree, and no boundary between them survived contact: `authz` already
imports the grant ORM, builds SQL against application models, and holds a
session-aware cache, so the "pure engine" separation the docstrings describe
does not exist in the code. One module means one place to look and one answer
to any authorization question.

The cost is 1,324 lines relocated or dissolved, 19 `user_can_project_action`
call sites across 10 files, and the imports in the 16 files that reach into
`data_authorization` today.

**Until then, no rule in this document can be assumed enforced merely
because `authz/policies.py` states it correctly.**

**D-6 — Hospital scope is still writable.**
Accepted on write and handled throughout the containment logic in both
modules. No hospital-scoped grant exists in the data.

### Roles

**D-7 — Verification is authorized by four roles, not one.**
`VERIFICATION_ROLES` is `{verifier, admin, local_admin, fileUploader,
data_manager}`. Under this document it narrows to `{verifier, admin}`.

Eight active users verified without holding either role at audit time. Three
held only `fileUploader`; five held `data_manager`, four of those alongside
`ophthalmologist` and two alongside `fileUploader`.

Operational prerequisite: **every active `data_manager` holder missing
`verifier` is granted it** by a one-time role-based query. This covered five
users. The three `fileUploader`-only holders were not granted it and stop
verifying when the role set narrows, which is the intent of the rule.

Run the grant **before** narrowing the role set, or the five lose the ability
the moment it narrows.

**D-8 — The field roles do not mirror the clinic split.**
`field_optometrist` and `field_ophthalmologist` authorize identical sets,
so a field ophthalmologist cannot grade where a clinic one can.

**D-9 — `data_exporter` cannot export project-owned data.**
Every dataset action sets `project_roles={dataset_creator}`, which replaces
the classical role list for project-owned rows. The role is named in
`dataset.export.create` and `.download` but reaches only unowned data.

**D-10 — Retired roles remain in the catalogue.**
`resident`, `principal_investigator`, `co_investigator` and `coordinator`
persist as rows in the `roles` table although they appear in no policy.

Two active users still hold `resident`, contradicting `42dbd416`, which
reported none did when it retired the role. Both also hold `ophthalmologist`.
`resident` migrates to
`ophthalmologist`: grant `ophthalmologist` where the holder lacks it, then
drop the `resident` holding, then drop the row. Both current holders already
have `ophthalmologist`, so today the migration only revokes - but it must be
written to add the role first, or a later holder acquired between now and the
migration silently loses the qualification to grade.

The `user_roles` foreign key means the holdings must go before the row can,
which `fundus_img_xtract-dwvi` does not yet account for.

### Actions

**D-11 — Verification accepts no project grant.**
All seven `verification.*` actions take only classical grants, so a lab-unit
assignment reaches project-owned encounters and a project grant confers
nothing. This is the one data-bearing mutation family that is not
dual-branch. Tracked as `fundus_img_xtract-evr3` (AUTHZ-04); note the fix is
a change to this policy and to `authz/policies.py`, not only to the route.

**D-12 — A project role grant still authorizes uploading.**
`PROJECT_UPLOAD_GRANTS` accepts `PROJECT_ROLE` and `LEGACY_PROJECT_CAPABILITY`
alongside `UPLOAD_PROFILE`, so a project role grant carrying an uploading role
authorizes ingestion without any upload profile. Under this document the
upload profile is the only route in, because it is what carries the kind, and
the grant is what carries the Lab Unit. The two non-profile grant sources come
out of the five `project.upload.*` policies.

**D-13 — `master_admin` / `is_master_admin` remains a parallel bypass.**
Asserted as a non-bypass since 2026-04-30 and never enforced. Tracked as
`fundus_img_xtract-guz4`.

**D-17 — Every dataset action is gated on `dataset_creator`.**
`authz/policies.py::_curation` sets `project_roles={dataset_creator}` for all
six dataset actions, so release is not yet separated from assembly. The three
release actions must take `data_exporter` instead, and `dataset_creator` must
lose them. `datasets/routes.py:600` also gates share OTP regeneration on
`dataset_creator`.

**D-18 — The finalised precondition is enforced but not declared.**
Three paths reject an unfinalised dataset independently - share creation
(`datasets/routes.py:348`), direct export (`analytics/route_dataset_curation.py:1458`)
and export regeneration (`jobs/routes.py:225`) - so the rule holds today by
deliberate checks rather than by accident of routing, as this entry previously
claimed. What is missing is that no `ActionPolicy` carries the precondition,
so a fourth release path would have to remember it. Debt, not a present gap.

**D-19 — Classical upload is unscoped at the route, and unrecorded.**
`auth/roles.py:156` short-circuits `global_uploader_or_project_assignment_required`
on `has_role("admin", "fileUploader")`, so a holder uploads any kind into any
Lab Unit of any hospital, with no assignment consulted.

The short-circuit returns before the engine runs, so the decision is never made
on evidence at all. `GrantSource.ADMIN_GLOBAL` is already evaluated inside the
engine (`authz/engine.py:70`), so removing the branch does not remove admin's
access - it makes that access a decision rather than an assumption.

It does not by itself make it *recorded*. `authorize()` emits no telemetry:
`record_authorization_decision` has one caller outside its own module,
`media/routes.py:201`. An earlier version of this entry claimed the engine
records every decision. It does not. Recording break-glass is additional work,
and worth doing precisely because break-glass on ingestion writes patient
records rather than reading them. The three classical
create actions - `upload.direct.create`, `upload.pregraded.create`,
`upload.zip.create` - state the correct rule and have **no call sites outside
`authz/`**: they are registered, correct, and never invoked. Under this
document classical uploading is bounded by the uploader's lab-unit
assignment, so the short-circuit goes and the actions must be wired.

**D-20 — An upload grant cannot express project-wide.**
`ProjectUploadProfileAssignment.lab_unit_id` is `NOT NULL`, so every upload
grant names exactly one Lab Unit and project-wide can only be approximated by
enumerating every configured one. Making the column nullable, with `NULL`
meaning project-wide, matches how `ProjectRoleGrant` already records scope.

**D-21 — Per-role scope invariants are not enforced.**
`data_authorization/service.py::_validate_scope_target` validates that a scope
is structurally coherent, not that the role may be granted at it. Nothing
rejects a project-scoped `site_pi` or a lab-unit-scoped `project_pi`; one of
the latter exists in the data today. The invariants above need enforcing on
write, and a test asserting no grant violates them.

**D-22 — `analytics_viewer` still reaches patient identifiers.**
`f9e3ffa8` removed it from `project.encountersets.browse_pii`, stating that
"authorization now agrees rather than leaving masking to do the work alone".
It was removed from `authz/policies.py` only. The live browser
(`remidio_api_integration/service.py::_apply_encounter_set_browser_scope`)
reads `data_authorization.policy.ACTION_ROLE_NAMES`, which still lists it.

No one is exposed today - both holders reach identifiers through another
role - but granting `analytics_viewer` to a user without a clinical role
would surface patient identifiers to a role defined as never seeing them.

**D-23 — `browse_pii` authorizes eleven roles; this document allows two.**
`authz` grants it to `data_exporter`, `dataset_creator`, `discrepancy_reviewer`,
`ophthalmologist`, `optometrist`, `regrade_adjudicator`, `verifier` and all
three governance roles - whose own definition at `authz/policies.py:150`
states "None of it includes patient identifiers". Every one of those except
`optometrist` and `verifier` does work that begins at or after grading.

The target is the set that handles record identifiers - capture, upload and
verification - which `MEDIA_PII_ROLES` already encodes for images: `admin`, `data_manager`, `fileUploader`, `local_admin`,
`optometrist`, `verifier`. Two definitions of who may see a patient
identifier become one. `browse` is untouched, so no role loses the ability to
browse - only to see identifiers while doing it.

**D-24 — An upload profile assignment authorizes uploading without any uploading role.**
`global_uploader_or_project_assignment_required` falls through to
`user_has_any_project_upload_assignment`, which asks only whether an active
assignment exists; the mutation service then validates the assignment and the
profile's clinical dimensions but never the actor's role
(`services/uploads/direct.py`, `upload_profiles/service.py`). Assignment
creation accepts any active user - `_validate_user_lab_assignment` checks that
the user is active and the Lab Units valid, not that they hold an uploading
role.

So an ordinary active user with no uploading role, assigned to a profile by
mistake or by an over-broad access manager, can ingest patient data. This is
the inverse of D-12 and D-19: those describe a role reaching past the profile,
this is a profile reaching past the role. Both bounds must hold.

**D-25 — The PII browser under-authorizes the users this document allows.**
`_apply_encounter_set_browser_scope` resolves roles only through project role
grants. A user who reaches a project solely through an upload profile
assignment - the `fileUploader`, `pregarded_uploader`, `data_manager` and
`local_admin` route this document permits for `browse_pii` - is not considered
at all. D-22 and D-23 are the over-authorization; this is the matching denial.

**D-26 — WAI authorization differs between the engines.**
`authz` permits `project.wai.results` to `project_pi`, `site_pi`,
`project_admin`, `optometrist`, `verifier`, `data_manager`, `analytics_viewer`,
`ophthalmologist` and the field roles. The live engine
(`data_authorization/policy.py`) permits only `project_pi`, `site_pi`,
`project_admin` and `optometrist`, and live API routes call it directly
(`api/remote_inference.py`). Field and clinical users this document authorizes
receive 403. Neither engine implements the upload-profile relationship this
document names for the WAI actions.

**D-27 — Dataset curation cannot correct what it must correct.**
Curation already filters on OCR results - `_apply_pii_filter` in
`analytics/route_dataset_curation.py` selects images where `pii_status` is
`detected` - so a curator finds every leaking image and can act on none of
them. `dataset_creator` is absent from `MEDIA_PII_ROLES`, so it cannot open
the detections, and there is no curation-side image-correction action
equivalent to `verification.direct.update`. Two changes: add
`dataset_creator` to the image-identifier roles, and give curation a
correction path.

That path is narrower than verification's. Curation edits the image and sets
the PII present/absent flag, and does nothing else: it does not verify, and it
creates no downstream task. Verification decides whether data may become
gradable work; curation only decides whether an image is clean enough to
leave.

**D-28 — PII detection does not record the context it ran in.**
`run_pii_detection_queue_task(self, max_jobs, user_id, hospital_id)` accepts
both scoping arguments and drops them: the body is
`run_pii_detection_queue(max_jobs=max_jobs)`. The queue itself filters only on
`PiiDetectionJob.status == "queued"`.

Global scanning is right - every image should be swept - so this is not an
over-reach. What is missing is that a detection job does not record whether it
was raised in a classical context or a project one, so its results cannot be
attributed to the boundary they belong to. Refactor so the context is carried
on the job and recorded with the result, rather than passed and discarded.

**D-29 — Raw EXIF is a patient-identifier path open to fifteen roles.**
`media.metadata.read` and `media.metadata.process` use `MEDIA_IMAGE_ROLES` -
every project role, `collaborator` and `analytics_viewer` included. The default
payload is technical only, but `include_raw: true` returns `exif_json`
(`api/image_metadata.py`), which is whatever the camera wrote.

Ingestion strips EXIF inconsistently: `zip_processor.py`, the IITK service and
the IITK EncounterSet importer all call `strip_exif_data`; direct uploads
(`services/uploads/direct.py`, `direct_uploads/save_image.py`), mobile uploads
(`services/uploads/mobile.py`) and Remidio API ingestion
(`remidio_api_integration/ingest.py`) call it nowhere. So for images arriving
by those routes the camera's tags are retained and readable.

Ruled 2026-08-26: EXIF is a patient identifier. Because removing it needs no
inspection, no workflow step requires its contents - the `exif_present` flag
is enough for anyone who needs to know an image is unclean. Two changes: strip EXIF on every ingestion path, and confine
`include_raw` to the roles that may read image identifiers. Whether identifiers
are in fact present in this deployment's retained EXIF has not been sampled and
should be, since it decides whether existing rows need remediation as well.

**D-30 — Hospital scope is an attribute pretending to be a relation.**
`authz/adapters.py:33` manufactures the grant from the user record:
`RelationshipGrant(source=GrantSource.HOSPITAL_SCOPE, hospital_id=actor.hospital_id)`.
There is no hospital relation - `users.hospital_id` is a single column, so a
user administers exactly one hospital, no row asserts that they administer it,
and the assertion cannot be granted, revoked or audited independently of the
user record.

This is D-1 one layer down: scope held as an attribute rather than as the
object of a relation. The consequence is the same, and it is already realised -
`verify_encounter_set/routes.py:136` decides `s3_config.hospital_id !=
current_user.hospital_id` and returns "Access denied to S3 storage" without
consulting the engine, so the decision is neither evaluated on evidence nor
recorded.

`local_admin` is retained: classical scoping is where most non-project work
still lives. What changes is that its hospital becomes a relation the engine
resolves, and `users.hospital_id` stops being read for decisions.

**D-31 — Pre-graded ingestion is gated on the wrong role.**
`direct_uploads/pregraded_grades.py:713` and `:1139` are
`@roles_required("fileUploader")`, so `pregarded_uploader` - the role named
for this work - cannot reach the pre-graded import at all, while the generic
uploading role can. The actions are wrong in the same direction:
`upload.pregraded.create` accepts `fileUploader` alongside
`pregarded_uploader`, and `project.upload.pregraded` accepts nine roles
including `fileUploader`, `optometrist` and `verifier`.

Under this document pre-graded ingestion requires `pregarded_uploader`, in
both the classical and project contexts. This compounds AUTHZ-05
(`fundus_img_xtract-mckk`), which is the same route carrying no
upload-profile or project authorization either: it admits the wrong role and
then checks nothing about the target.

**D-32 — `admin` has no break-glass on `grading.grades.view`.**
The action carries `roles={admin, ophthalmologist}` but `grants={SELF}` alone.
Grants are disjunctive, so a role with no matching grant source admits nobody:
`admin` is present in the role set and inert. This is the only action in the
registry where break-glass does not reach, and it is an omission rather than a
decision - `ADMIN_GLOBAL` belongs in its grant sources.

**D-33 — Nothing withholds an image flagged as carrying identifiers.**
`image_pii_verifications` records 4,262 images with `pii_status = detected`
- 4,261 found automatically and one recorded by hand - against 16,019 clear,
with 202 subsequently cleared by hand. No authorization
path consults the flag: `media/authorization.py`, `media/routes.py` and
`utils/utilsImgServe.py` contain no reference to `pii_status`, and nothing
anywhere refuses to serve a flagged image.

`media.image.view` carries `shows_pii=False` and fifteen roles including
`collaborator` and `analytics_viewer` - the two defined as never seeing
identifiers. Their safety therefore rests on the correction workflow having
been completed rather than on any gate, and D-27 records that dataset curation
can find these images and correct none of them.

Because image access converges on this one action (see *Image Access Is
Authorized On The Object*), the check belongs here and covers every viewer at
once. An image flagged `detected` and not since cleared is not served to a
role outside the image-identifier set, and `error` fails closed for the same
roles: an OCR failure means unknown, not clean.

Detection is an OCR result, so some of the 4,261 will be false positives -
device labels, laterality markers, dates. The count is an upper bound on
exposure; the absence of any check is not.

**D-34 — `media.pdf.view` admits post-grading roles and excludes pre-grading ones.**
`MEDIA_DOCUMENT_ROLES` is `admin`, `data_exporter`, `data_manager`,
`fileUploader`, `local_admin`, `ophthalmologist`, `optometrist`. A report PDF
carries record identifiers and is read during the pre-grading steps, so the
set should be `verifier`, `optometrist`, `field_optometrist`,
`field_ophthalmologist` and `admin`. `verifier` and both field roles cannot
read a report today; `ophthalmologist`, `data_exporter`, `data_manager` and
`fileUploader` can.

**D-35 — `inference.wai.rows` carries the analytics role set.**
Its disclosure flag is correct: policy construction sets `shows_pii=True`.
An earlier version of this entry claimed otherwise and was wrong.

Its roles are the analytics cluster - `analytics_viewer`, `local_admin`,
`ophthalmologist`, `optometrist` among them - because `.rows` inherited its
shape from `.summary`. Inference runs at capture, so the set is
`fileUploader`, `verifier`, `data_manager`, `field_optometrist`,
`field_ophthalmologist` and `admin`. Four roles gain nothing they should have;
`fileUploader` cannot read rows for uploads it made.

**D-36 — A retrospective inference run is authorized as though it were a capture.**
`remote_inference/manual_service.py::list_manual_wadhwani_projects` defaults to
`action="project.wai.run"`, the capture-time action, and
`remidio_api_uploads/wadhwani_inference.py:369` calls it that way. So a manual
re-run over existing records is gated on `optometrist`, `verifier` and the
field roles, while `data_manager` - whose work it is - cannot start one.

Retrospective runs need their own action, held by `data_manager` with `admin`
as break-glass, distinct from `project.wai.run` and `inference.wai.run`.
`inference.wai.retry` (`admin`, `data_manager`, `local_admin`) is already
shaped correctly and is the model to follow.

**D-37 — The identifier classification is inert.**
`ActionPolicy.shows_pii` and `action_shows_pii()` exist in
`authz/policies.py` and have **no consumer anywhere else in the codebase**.
Twenty-two actions are classified as showing identifiers and nothing reads
the classification, so marking an action `shows_pii=True` masks nothing.

`f9e3ffa8` built the classification and stated its purpose - that identifier
visibility must be a property of the action rather than of the actor's roles,
because deciding it from roles had unmasked seven of twenty-one users
everywhere. The classification is correct and unused.

It is also incomplete, which matters more while it is the only written record
of the disclosure surface. `media.metadata.read` is flagged `shows_pii=False`
and carries the camera's raw tags (D-38); `media.image.view` is flagged
`shows_pii=False` and serves images with identifiers burned in. A test that
asked the flag whether a collaborator reaches identifiers would answer no on
both. `IDENTIFIER_CHANNELS` in `tests/unit/authz/test_role_catalogue.py` names
the channels one by one instead, and is the list to review.

This invalidates a mechanism relied on elsewhere in this document: nowhere can
a rule be satisfied by declaring an action identifier-bearing and expecting
masking to follow. Until a consumer exists, every identifier rule must be
enforced by the role set on the action, by a separate action, or by not
serving the field.

**D-38 — Raw EXIF cannot be confined by a role set on the current action.**
`api/image_metadata.py` authorizes `media.metadata.read` once and then
serializes ordinary metadata or, on `include_raw`, the EXIF tags. Technical
metadata is legitimately readable by every image-authorized role and the tags
are not, so no single static role set on that action satisfies both rules:
narrow it and collaborators lose dimensions and DPI; leave it and they can ask
for the tags.

A contextual condition evaluated at the `include_raw` branch would also confine
it, but no such mechanism exists here: `ActionPolicy` carries static roles,
grants and scope, `authorize()` has no condition callback, and `shows_pii` is
inert (D-37). A second action is therefore the cheapest coherent design
available, not the only conceivable one.

**D-39 — Break-glass is missing from four actions that should have it.**
Seventeen authenticated actions do not accept `ADMIN_GLOBAL`; the seven deliberately public actions are outside this count. Thirteen are deliberate: ten
`SELF`-scoped personal actions, and the three grading submissions which take
`GRADING_SLOT` alone.

The remaining four are gaps. `grading.grades.view` carries `admin` in its role
set with `SELF` as its only grant source, so the role is inert (this is D-32).
`upload.direct.create`, `upload.pregraded.create` and `upload.zip.create` take
`UPLOAD_PROFILE` alone and do not name `admin` at all, so break-glass does not
reach ingestion.

The global rule that upload access comes from profiles "not by admin,
local-admin, data-manager or hospital scope alone" describes the ordinary
path. It was read as excluding `admin` entirely, which is not the intent.

**D-40 — An upload assignment alone grants project entry, with no role.**
`data_authorization/policy.py` resolves `project.view` as a project role grant
**or** `_has_any_upload_assignment(...)`, and that function checks project,
profile and assignment state without ever consulting the actor's role. The live
chain is `/projects/<id>/summary|uploads|gradings` -> `project_capabilities()`
-> `data_authorization.policy`.

So a user holding no qualifying role, left with an active profile assignment,
reaches the project overview and its upload and grading summaries. This is
D-24's defect on a second action: a profile assignment standing in for a role.
Both bounds must hold here too.

**D-41 — `pii_exporter` does not exist.**
The catalogue names it and the release rules require it, but it is absent from
`auth.roles.DEFAULT_ROLES`, from every policy in `authz/policies.py`, and from
the `roles` table. There is no identifier-bearing release action for it to
hold either.

So the two-role egress control this document specifies cannot be configured:
an implementer must create the role and the action, or silently keep the
single-role release path. Until both exist, every rule requiring
`pii_exporter` is unimplementable rather than merely unimplemented.

The catalogue test did not catch this. It asserted every role in
`DEFAULT_ROLES` has a documented purpose and never the reverse, so a purpose
written for a role that does not exist passed.

**D-42 — The Glaucoma AI actions are documented, registered and unused.**
None of `glaucoma_ai.result.view`, `glaucoma_ai.upload.create` or
`glaucoma_ai.workspace.view` has a production consumer. The live web and token
gates use role decorators that omit `pregarded_uploader`
(`glaucoma_ai/routes.py:20`, `api/glaucoma_ai.py:35`); result queries are
scoped to the uploading owner rather than to a Lab Unit or project as the
action rules claim (`api/glaucoma_ai.py:435`); and upload creation delegates
straight to upload-profile validation without invoking
`glaucoma_ai.upload.create`.

`pregarded_uploader` appeared in the executable policies for all three and was
briefly copied into this document to match them. That was backwards. The role's
purpose is pre-graded ingestion - identifying the model whose grades these are
and mapping the source sheet onto the grade catalogue - and Glaucoma AI
submission is direct-image capture and inference. The rules no longer name it,
and the executable policies should drop it too unless the role's purpose is
deliberately widened.

**D-43 — Break-glass ingestion has no profile to resolve.**
Adding `admin` and `ADMIN_GLOBAL` to the upload create actions is necessary and
not sufficient. `upload_profiles/service.py::validate_upload_scope` resolves
profiles from the actor's own assignments, so an administrator acting under
break-glass presents no assignment and the service finds nothing to validate
against. A separate resolver is needed - one that validates the *selected*
profile is active and configured for the target, rather than that the actor is
assigned to it.

Recording is a second gap. The rule above requires break-glass ingestion to be
recorded, and `authorize()` emits no telemetry (D-19), so a caller must record
it explicitly as `media/routes.py:201` does.

**D-44 — Clinical aggregates are not project-gated.**
`_aggregate_kpi()` sets `project_gated=False` for every aggregate, including
`dr-results-distribution`, `glaucoma-results-distribution` and
`vcdr-distribution`. Those are a project's clinical findings, not a Lab Unit's
throughput, and the reasoning that justifies ungating a capture count does not
extend to them. They need the dual-branch treatment the `.rows` actions have.

**D-45 — Grade exports are not distinguished from data exports.**
No action separates exporting a site's own encounters and images from
exporting the grades human graders made on them, so nothing can withhold one
while permitting the other. `site_pi` sits in `PROJECT_OVERSIGHT_ROLES` and
therefore in `ANALYTICS_ROLES`, reaching `analytics.kpi.*.rows` alongside
`project_pi` unconditionally; a lab-unit-scoped `data_exporter` is likewise
unconstrained.

Both need the same treatment: a site's own data stays freely exportable, and
grade export becomes conditional on `sites_can_export_grades` (D-48) together
with `data_exporter`. That requires the grade columns to be separable from the
encounter columns in the export paths, which the current dataframes do not do -
`dr_result`, `glaucoma_result` and the VCDR values sit in the same row as the
encounter's own fields.

Note this does *not* separate `site_pi` from `project_pi` by action set. Both
hold the same actions; they differ by the scope they are granted at and by the
settings that scope brings with it. The `KNOWN_DUPLICATE_GROUPS` exemption in
`test_role_catalogue.py` therefore stays, and the duplicate-role test cannot be
the thing that tells these two roles apart.

**D-46 — A user administers exactly one hospital.**
`users.hospital_id` is a single column, so `local_admin` cannot administer more
than one hospital however many it should. The relation model in D-30 is what
allows several; until then the limit is structural, not a matter of what has
been granted.

**D-47 — Field grading has no slots.**
`field_ophthalmologist` carries the clinical qualification but grading is
reached through a grading slot, and no slots are allocated for field work. The
role will grade nothing until they are, so allocating them is part of giving
the field roles their clinic counterparts' distinction (`fundus_img_xtract-h0kz`).

**D-48 — There are no per-site settings.**
`sites_can_export_grades`, `sites_can_create_datasets` and
`sites_can_share_datasets` do not exist. `ProjectLabUnit` - the project-to-Lab-
Unit binding where they belong - carries only `project_id`, `lab_unit_id` and
`active`. The per-project capability flags that do exist -
`can_export_data`, `can_create_datasets` and six more on
`ProjectEncounterSetPermission` - are a different construct: per-user legacy
capability grants, the `LEGACY_PROJECT_CAPABILITY` source that
`fundus_img_xtract-xwwk` retires. They grant capability to a person; these
settings restrict what any site-scoped holder may do.

Until the settings exist, the project-object condition on curation and release
is absolute in code, so no project can permit site-level datasets or grade
exports even where that is the intended arrangement. The grade XLSX export
paths in particular are gated by role alone.

### Assurance

**D-14 — Route enforcement is not proven.**
Parity tests assert that registered actions have policies, not that routes
invoke them. Every finding in the 2026-08-25 surface audit survived a green
suite. The route-to-action coverage test in `fundus_img_xtract-guz4` is what
closes this, and it is the highest-leverage item in the epic. D-49 is the part
of it that has now been measured.

**D-49 — Eighty-three of the 121 actions are named nowhere in application code.**
Parsing every application module for mentions of a registered action name -
written as a literal or reached through a module constant, excluding `authz`
itself, which defines them - finds 38 actions. The other 83 carry a rule, a
role set and an identifier classification that nothing reads.

Mentions are counted, not decisions, so 38 is the generous figure. Of those,
34 reach a function that decides: the action is passed to the engine, to the
second engine, as an `action=` parameter default a wrapper enforces with, or
positionally to a wrapper one hop from the engine. The four that do not are
the `project.upload.*` actions, which `data_authorization/policy.py` dispatches
on as keys of `UPLOAD_ACTION_KIND` - enforcement the scanner cannot see through
a dict, and a known false negative.

Flask endpoints share the `blueprint.function` shape of some action names, and
the count excludes them: every mention of `auth.login` in this codebase is
`url_for("auth.login")` or `login_manager.login_view = "auth.login"`, twelve of
them, none a decision.
Whole domains are inert: all 8 `mobile.*`, all 5 `intra_rater.*`, all 4
`grading.*`, all 3 `glaucoma_ai.*` (D-42), 6 of 7 `verification.*` (D-7), 8 of
9 `admin.*`, and all 4 `auth.*`.

Fifteen of the 83 are classified as showing identifiers, among them every
`verification.*` view and update except the EncounterSet one, and every
`upload.*` action except `upload.direct.view`. Their routes are not
unprotected - `verify_encounter_set/routes.py:152` onward is gated by
`@roles_or_project_grant_required("admin", "optometrist", "data_manager")` -
but they are protected by a role decorator naming roles directly, not by the
action whose rule this document states. Two mechanisms, and the rules describe
the one that decides less.

This is the measured form of D-14. It is recorded separately because it is not
an absence of proof: for these 83 the policy row is proven inert.

`tests/unit/authz/_call_sites.py` builds both indexes; the identifier-channel
tests in `test_role_catalogue.py` refuse to treat an action as a control until
it reaches a decision function.

Neither index closes D-14. Reaching a decision function is not evidence that
the decision happens before the identifier is serialized, or that every route
producing one goes through it. That still needs route-to-action coverage.

**D-50 — `admin` grades without the clinician role.**
The global rules say a grading submission requires the grading slot itself,
because the `admin` role does not stand in for the clinician role, and that an
administrator who should grade holds a slot. `GRADER_ROLES` in
`authz/policies.py:191` is `{ophthalmologist, admin}`, and the engine requires
the actor's roles to intersect it - so `admin` plus a slot submits a clinical
grade without `ophthalmologist`. The three `grading.*.submit` rules state the
code's position, naming `admin` as a grader role.

The two readings agree that a slot is required and disagree on whether the
clinical qualification is. That is a clinical governance decision rather than a
drafting one: it decides whether a system administrator with a slot may enter a
diagnosis of record. `fundus_img_xtract-2hgv` proposes separating a
`main_admin` from clinical grading roles and slots, which is the same question.

Until it is settled the rules are left as they stand, named in
`GRADING_ROLE_UNSETTLED` in `tests/unit/authz/test_role_catalogue.py` so the
list empties itself when the rules and the model agree.

**D-51 — Project grader-allocation authority is not modelled.**
The approved policy separates three actions: viewing an allocation plan,
managing contained allocations, and switching project-wide enforcement. None
is registered in `authz/actions/*.toml` or represented in `authz/policies.py`.

The live layers also disagree. `api/grading_allocations.py` admits only the
user-level `admin` role, while `grading_allocation/service.py` accepts
`admin`, `local_admin` or `data_manager` and derives reach from classical Lab
Unit assignments intersected with the project's configured Lab Units. Neither
path asks for the project role grant decided above. The service lets any such
Lab Unit-scoped manager toggle enforcement for the whole project, and its
candidate test accepts the retired `resident`, `resident2` and `arbitrator`
role names rather than `ophthalmologist` plus a matching active grading slot.

Migration must add the three actions, resolve managers through project grants,
apply containment to allocation writes, require project scope for the policy
toggle, and derive effective candidates and coverage from the clinical role
and slot. Until then, the allocation UI and service implement an older policy.

**D-52 — System and user administration are not separated.**
The approved model reserves system administration to `admin` and introduces
hospital-scoped `user_manager` for user records, ordinary roles, Lab Unit
assignments, grading slots, enrolled devices and sessions. The role is absent
from `auth.roles.DEFAULT_ROLES`, the action policies and the database seed.

The live admin routes still admit `local_admin` to user CRUD and mobile-device
management (`admin/users.py`), admit `local_admin` or `data_manager` to several
status, package, quota, grading and maintenance routes, and the registered
`admin.dashboard.view`, `admin.grading_eligibility.manage`,
`admin.users.*` and `api.mobile.session.manage` policies encode the older role
sets. Migration must first add `user_manager` and its hospital relationship,
then move only the user-centred actions to it and make every remaining system
administration route `admin` only. The user-manager write path must prevent
managing or granting `admin` or `user_manager` and must not write project
grants or grader allocations.

**D-53 — Public analytics is hidden inside a generic public gate.**
`public/analytics.py` deliberately serves unauthenticated system-wide
aggregates, but `app.py` exempts the `/analytics` page and every
`/api/analytics/` prefix while the registry exposes only `public.view`. The
authenticated KPI actions are separate, but the public surface has no action
of its own and the prefix exemption can silently admit a future API. The clean
model needs `public.analytics.view` for the exact page and approved aggregate
endpoints; it must not inherit patient rows, exports or project clinical-result
drill-downs from KPI analytics.

**D-54 — Discrepancy export has no separate identifier-bearing action.**
`review.discrepancy.export` currently creates the export for `admin`,
`data_manager` or `data_exporter`. `include_original_filename` is a form flag
special-cased to `admin`, although an original filename can itself carry a
patient identifier. There is no `review.discrepancy.export_pii` action and
`pii_exporter` is not enforced. Migration must make the ordinary export masked,
require the separate action plus additive `pii_exporter` for identifier-bearing
files, and preserve the base task scope in both paths.

**D-55 — Notification sending has no action policy.**
The registry covers only self-scoped notification view and update. Live compose,
peer, administrator, broadcast and system-send routes use inline relationship
queries or `admin` decorators, so their sender and recipient authority cannot
yet converge on the engine. The policy decision is intentionally deferred;
these routes must not be migrated until their action and recipient rules are
written.

**D-15 — Upload eligibility helpers disagree.**
Some paths expand admin to all lab units while profile-based access requires
explicit assignment. Wiring must preserve the profile-assignment rule.

**D-16 — Withdrawn.** Inherited from the pre-2026-08 conflicts list and not
verified when this register was written. Signed media routes validate the
exact credential and the exact object, and the legacy routes call the same
object-authorization layer (`media/routes.py`, `utils/utilsImgServe.py`,
`media/authorization.py`). There are two entry paths but one decision, so
there is no divergence to reconcile.

### Closed

- `admin/uploads.py` malicious-upload view had no auth decorator — fixed in
  `036d7891` with 28 other admin routes.
- Grading decorators named `resident2` and `arbitrator` as roles — resolved
  in `42dbd416`: both are slot names, both actions are now registered, and
  the `resident` role is retired.
- `/dashboard/*` was login-only and globally unscoped (AUTHZ-01) — fixed in
  `7c53873d`.
- Legacy EncounterSet grading bypassed allocation (AUTHZ-02) — fixed in
  `748dd8ab` and `f25d9272` by deleting the transport.

# Registered Action Rules

**Every `- Rule:` line below states the policy as it must be, not as the code
currently behaves.** Where the two differ the difference is a numbered entry in
[Divergences To Reconcile](#divergences-to-reconcile) and nowhere else. A rule
here is never a description of current behaviour, so a reader implementing an
action follows the rule and consults the register only to learn what still has
to change.

Every action in `authz/actions/*.toml` has an executable policy in `authz/policies.py` and a rule below. The registry test enforces that correspondence in both directions.


## Domain: account

### `account.password.change`

- Rule: A user may change the authenticated user's password only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: user (required).

### `account.profile.update`

- Rule: A user may update the authenticated user's account profile only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: user (required).

### `account.profile.view`

- Rule: A user may view the authenticated user's account profile only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: user (not required).

## Domain: ad_hoc_tasks

### `ad_hoc_task.create`

- Rule: A user may create ad hoc grading tasks from scoped image search results when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: ad_hoc_task_batch (required).

### `ad_hoc_task.delete`

- Rule: A user may delete or cancel ad hoc task batches when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: ad_hoc_task_batch (required).

### `ad_hoc_task.view`

- Rule: A user may view ad hoc task creator pages and created batches when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: ad_hoc_task_batch (not required).

## Domain: admin

### `admin.dashboard.view`

- Rule: Only `admin` may view system-administration dashboards and status pages.
- Relationship source: admin-global scope.
- Resource: admin_dashboard (not required).

### `admin.grading_eligibility.manage`

- Rule: `admin` may manage grading eligibility and slot assignments across hospitals; `user_manager` may manage them only for ordinary users in the manager's own hospital.
- Rule: `user_manager` may not manage `admin` or another `user_manager` through this action.
- Relationship source: admin-global scope, or the target user's hospital matching the user manager's hospital.
- Resource: grading_slot (not required).

### `admin.lookup.manage`

- Rule: Only `admin` through admin-global scope may manage lookup tables such as hospitals, lab units, diseases, cameras, and areas.
- Relationship source: admin-global scope.
- Resource: lookup (not required).

### `admin.s3.manage`

- Rule: Only `admin` through admin-global scope may manage S3 configuration and S3 sync administration.
- Relationship source: admin-global scope.
- Resource: s3_config (not required).

### `admin.security.view`

- Rule: Only `admin` through admin-global scope may view security, audit, CVE, log, and sensitive-operation administration pages.
- Relationship source: admin-global scope.
- Resource: security_event (not required).

### `admin.system.manage`

- Rule: Only `admin` through admin-global scope may manage system operations including database, Celery, packages, thumbnails, disk usage, and rate limits.
- Relationship source: admin-global scope.
- Resource: system_operation (not required).

### `admin.upload_profiles.manage`

- Rule: Only `admin` through admin-global scope may define upload projects and profiles or change their configuration and activation. Assigning users to an existing project profile is the separate contained `project.uploaders.manage` action.
- Relationship source: admin-global scope.
- Resource: upload_profile (not required).

### `admin.users.manage`

- Rule: A user may create or change an ordinary user record only when the actor has `admin` or `user_manager`.
- Rule: `admin` manages users in every hospital; `user_manager` manages only ordinary users in its own hospital.
- Rule: `user_manager` may assign ordinary non-project roles and Lab Units, but may not manage or grant `admin` or `user_manager`, project grants or project grader allocations.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: `local_admin` and `data_manager` are deliberately excluded: they administer hospital operations and workflow, not accounts.
- Rule: A user record belongs to a hospital and to no lab unit or project, so lab-unit assignment and project grants never reach it.
- Relationship source: admin-global scope, or the actor's own hospital.
- Resource: user (required).

### `admin.users.view`

- Rule: A user may view user records, allocations and activity only when the actor has `admin` or `user_manager`.
- Rule: `admin` reaches users in every hospital; `user_manager` reaches only ordinary users in its own hospital.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: `local_admin` and `data_manager` do not inherit user visibility from their operational roles.
- Relationship source: admin-global scope, or the actor's own hospital.
- Resource: user (not required).

## Domain: analytics

The actions in this domain are authenticated KPI analytics. They are not the
anonymous public analytics surface: `public.view` currently covers that surface,
and D-53 records why the redesign must give it its own action.

### `analytics.encounters.view`

- Rule: A user may view encounter analytics only when the user has one of `admin`, `local_admin`, `data_manager`, `analytics_viewer`, or `ophthalmologist` and the encounter is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Rule: A project's governance roles - `project_pi`, `site_pi`, `project_admin` - and `collaborator` also read these figures for their own project, as oversight of how it is going.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `encounter`.

### `analytics.hospital_dashboard.view`

- Rule: A user may view the hospital dashboard and its aggregate disease, lab, user and roster views when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the hospital.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: A project's governance roles - `project_pi`, `site_pi`, `project_admin` - and `collaborator` also read these figures for their own project, as oversight of how it is going.
- Rule: Not project-gated; the dashboard reports the hospital's own activity.
- Rule: Any drill-down that returns rows must use a project-gated action.
- Relationship source: classical scope.
- Resource: hospital (not required).

### `analytics.kpi.direct_files.rows`

- Rule: A user may read or export the per-image direct-upload dataframe for a row outside every project when hospital scope or an explicit lab-unit assignment covers it.
- Rule: A row owned by a project requires an explicit project role grant or legacy project capability for that project.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: classical scope for unowned rows; project authority for owned rows.
- Resource: direct image upload (not required).

### `analytics.kpi.direct_files.view`

- Rule: A user may view aggregate direct-upload KPIs and upload metrics when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the lab.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: A project's governance roles - `project_pi`, `site_pi`, `project_admin` - and `collaborator` also read these figures for their own project, as oversight of how it is going.
- Rule: Not project-gated, on the same basis as the encounter-file aggregates.
- Relationship source: classical scope.
- Resource: direct image upload (not required).

### `analytics.kpi.encounter_files.rows`

- Rule: A user may read or export the per-image encounter-file dataframe for a row outside every project when hospital scope or an explicit lab-unit assignment covers it.
- Rule: A row owned by a project requires an explicit project role grant or legacy project capability for that project. Lab-unit assignment alone never reaches it.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: classical scope for unowned rows; project authority for owned rows.
- Resource: encounter file (not required).

### `analytics.kpi.encounter_files.view`

- Rule: A user may view aggregate encounter-file KPIs when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the lab.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: A project's governance roles - `project_pi`, `site_pi`, `project_admin` - and `collaborator` also read these figures for their own project, as oversight of how it is going.
- Rule: This action is deliberately not project-gated. A count of what a lab captured is a fact about that lab's own throughput, so project-owned images in the user's labs are counted without a project relationship.
- Rule: This applies only to counts and distributions. Rows, identifiers and exports use `analytics.kpi.encounter_files.rows` and stay project-gated.
- Relationship source: classical scope.
- Resource: encounter file (not required).

### `analytics.upload_stats.view`

- Rule: A user may view aggregate upload counts for today and the last seven days when the user has one of `admin`, `analytics_viewer`, `data_manager`, `local_admin`, `ophthalmologist` and hospital scope or an explicit lab-unit assignment covers the lab.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: A project's governance roles - `project_pi`, `site_pi`, `project_admin` - and `collaborator` also read these figures for their own project, as oversight of how it is going.
- Rule: Not project-gated; these are counts of a lab's own intake.
- Relationship source: classical scope.
- Resource: direct image upload (not required).

## Domain: api

### `api.lookups.manage`

- Rule: Only `admin` through admin-global scope may mutate API-managed lookup or configuration resources.
- Relationship source: admin-global scope.
- Resource: lookup (required).

### `api.lookups.view`

- Rule: A user may read API lookup data such as hospitals, lab units, diseases, grades, AI models, and scoping context when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: lookup (not required).

### `api.mobile.session.manage`

- Rule: `admin` may issue device enrolment codes, approve or block devices, and revoke mobile sessions for any user; `user_manager` may do so only for an ordinary user in the manager's own hospital.
- Rule: Blocking an enrolled device revokes its active sessions. Administrative management is attributable to the administrator and does not impersonate the target user.
- Rule: The self-scoped `mobile.session.view` and `mobile.session.revoke` actions remain the only path by which a user manages their own sessions.
- Relationship source: admin-global scope, or the target user's hospital matching the user manager's hospital.
- Resource: mobile_session (not required).

### `api.ocr.manage`

- Rule: A user may read, override, or batch-process OCR/PII metadata when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: image (not required).

### `api.viewer_settings.manage`

- Rule: A user may read and mutate authenticated viewer settings and presets only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: viewer_settings (not required).

## Domain: audit

### `audit.data_quality.view`

- Rule: Only `admin` through admin-global scope may view cross-system data-quality audit reports such as encounters missing a capture date.
- Relationship source: admin-global scope.
- Resource: encounter (not required).

## Domain: auth

### `auth.login`

- Rule: This action is deliberately public: Public login and session creation action. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: session (not required).

### `auth.logout`

- Rule: This action is deliberately public: End an authenticated web session. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: session (not required).

### `auth.password_reset`

- Rule: This action is deliberately public: Public password reset request and completion flow. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: user (not required).

### `auth.reauth`

- Rule: A user may confirm password before a sensitive authenticated operation only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: session (not required).

## Domain: dashboard

### `dashboard.home.view`

- Rule: A user may view the authenticated landing page when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: none (not required).

### `dashboard.view`

- Rule: A user may view the hospital dashboard and its image listings when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: hospital (not required).

## Domain: datasets

### `dataset.curation.update`

- Rule: A user may update curated dataset membership, screening state, and metadata for a row that belongs to no project when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Rule: A user may update a row owned by a project only when the user holds `dataset_creator` on that project through a project-wide role grant. Curation spans the project, so a lab-unit-scoped grant confers nothing and lab-unit assignment alone never reaches a project row.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset (required).

### `dataset.curation.view`

- Rule: A user may view dataset curation screens for a row that belongs to no project when the user has one of `admin`, `analytics_viewer`, `data_exporter`, `data_manager`, `dataset_creator`, `local_admin` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the row.
- Rule: A user may view dataset curation screens for a row owned by a project only when the user holds `dataset_creator` or `data_exporter` on that project through a project-wide role grant. A releaser must be able to inspect what it is releasing. A grant scoped to one lab unit or one hospital of the project does not authorize curation of the project's data, and lab-unit assignment alone never reaches a project row.
- Rule: Legacy project capability rows do not confer dataset curation.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset (not required).

### `dataset.delete`

- Rule: A user may delete a curated dataset that belongs to no project when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Rule: A user may delete a row owned by a project only when the user holds `dataset_creator` on that project through a project-wide role grant. Curation spans the project, so a lab-unit-scoped grant confers nothing, a hospital grant confers nothing, and lab-unit assignment alone never reaches a project row.
- Rule: Legacy project capability rows do not confer dataset curation.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset (required).

### `dataset.export.create`

- Rule: A user may create a dataset export job for rows that belong to no project when the user has one of `admin`, `data_exporter` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Rule: A user may create an export job for a row owned by a project only when the user holds `data_exporter` on that project through a project-wide role grant. Release may draw on part of a project's data or all of it, so it carries the project's whole scope exactly as curation does. Curation spans the project, so a lab-unit-scoped grant confers nothing, a hospital grant confers nothing, and lab-unit assignment alone never reaches a project row.
- Rule: Only a curated and finalised dataset may be released. An unfinalised dataset cannot be exported or shared, whoever holds the role.
- Rule: `verification_remarks` is free text and travels with an export. Nothing constrains what a verifier types into it, so no column review and no masking layer can guarantee it is free of identifiers. This is an accepted risk, recorded here so it is a decision rather than an oversight: the field is useful to recipients and the alternative is dropping clinical context that has no other home.
- Rule: A release carries no staff personal data. Uploader and verifier names and usernames are dropped from exports; where provenance must travel, it travels as an opaque identifier. This is personal data about employees, held under a different obligation from patient data and needed by neither recipient nor analysis.
- Rule: Legacy project capability rows do not confer dataset curation.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset (required).

### `dataset.export.download`

- Rule: A user may download a generated dataset export file for rows that belong to no project when the user has one of `admin`, `data_exporter` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Rule: A user may download an export of a row owned by a project only when the user holds `data_exporter` on that project through a project-wide role grant. Release may draw on part of a project's data or all of it, so it carries the project's whole scope exactly as curation does. Curation spans the project, so a lab-unit-scoped grant confers nothing, a hospital grant confers nothing, and lab-unit assignment alone never reaches a project row.
- Rule: Only a curated and finalised dataset may be released. An unfinalised dataset cannot be exported or shared, whoever holds the role.
- Rule: Legacy project capability rows do not confer dataset curation.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset_export (required).

### `dataset.finalize`

- Rule: A user may finalize or unfinalize a curated dataset that belongs to no project when the user has one of `admin`, `dataset_creator` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Rule: A user may finalize or unfinalize a row owned by a project only when the user holds `dataset_creator` on that project through a project-wide role grant. Curation spans the project, so a lab-unit-scoped grant confers nothing, a hospital grant confers nothing, and lab-unit assignment alone never reaches a project row.
- Rule: Legacy project capability rows do not confer dataset curation.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset (required).

### `dataset.public_download`

- Rule: This action does not use a logged-in user's roles. It requires the exact active, unexpired dataset share named by a valid token, successful OTP verification, accepted terms, and the exact export job belonging to that share's dataset.
- Rule: The share reaches no other dataset and cannot add identifiers to the release. A share whose files contain patient identifiers must have been created through a release authorized by `pii_exporter` in addition to the base export role.
- Relationship source: the active share capability, OTP-verified recipient session and exact dataset relationship; no authenticated-user relationship.
- Resource: dataset_share (required).

### `dataset.share.manage`

- Rule: A user may create, toggle, regenerate, or administer shares of a dataset that belongs to no project when the user has one of `admin`, `data_exporter` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Rule: A user may share a row owned by a project only when the user holds `data_exporter` on that project through a project-wide role grant. Release may draw on part of a project's data or all of it, so it carries the project's whole scope exactly as curation does. Curation spans the project, so a lab-unit-scoped grant confers nothing, a hospital grant confers nothing, and lab-unit assignment alone never reaches a project row.
- Rule: Legacy project capability rows do not confer dataset curation.
- Relationship source: classical scope for unowned rows; project-wide project authority for owned rows.
- Resource: dataset_share (required).

## Domain: discrepancy_review

### `review.discrepancy.export`

- Rule: A user may create or download masked discrepancy review exports when the user has one of `admin`, `data_exporter`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers every exported task.
- Rule: Queue visibility and `discrepancy_reviewer` do not confer export. Release requires this action independently of review.
- Rule: An export containing original filenames or any other patient identifier is `review.discrepancy.export_pii` and additionally requires `pii_exporter`; it preserves the same task scope and may not widen it.
- Relationship source: classical scope.
- Resource: discrepancy_export (not required).

### `review.discrepancy.view`

- Rule: A user may view discrepancy review queues and task comparison data when they hold `discrepancy_reviewer`, or `admin` as break-glass.
- Rule: A `discrepancy_reviewer` acts within their defined scope - the Lab Units assigned to them outside a project, and the project or Lab Unit their grant names inside one. Scope decides which tasks they reach, never whether they may act.
- Rule: Reviewing a discrepancy is not resolving it. Creating regrade work needs `data_manager`; adjudicating it needs `regrade_adjudicator`. Neither is conferred here.
- Relationship source: lab-unit assignment outside a project; project role grant at either scope inside one.
- Resource: grading_task (not required).

### `review.regrade.adjudicate`

- Rule: A user may adjudicate a regrade and submit the adjudicated grade when the user holds either `regrade_adjudicator` or `admin`, and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the task.
- Rule: Either role suffices on its own; the two are not required together.
- Rule: Unlike the grading slots, regrade adjudication has no per-disease or per-lab slot, so no allocation is consulted.
- Rule: Site administration alone does not confer regrade adjudication.
- Relationship source: classical scope.
- Resource: grading task (not required).

### `review.regrade_creator.manage`

- Rule: A user may create and reallocate regrade tasks when they hold `admin`, or hold `data_manager`.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: A `data_manager` acts within their defined scope - the Lab Units assigned to them outside a project, and the project or Lab Unit their grant names inside one. Scope decides which tasks they reach, never whether they may act.
- Rule: Creating regrade work is separate from performing it. `data_manager` creates and reallocates; adjudicating the regrade needs `regrade_adjudicator` (`review.regrade.adjudicate`). Neither role performs the other's step, and holding one confers nothing of the other.
- Relationship source: admin-global scope; lab-unit assignment outside a project; project role grant at either scope inside one.
- Resource: grading_task (not required).

### `review.task.submit`

- Rule: A user may submit discrepancy review decisions for a grading task when the user has one of `admin`, `discrepancy_reviewer` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: grading_task (required).

### `review.task.view`

- Rule: A user may view task review detail pages and review viewer images when they hold `discrepancy_reviewer`, or `admin` as break-glass.
- Rule: A `discrepancy_reviewer` acts within their defined scope - the Lab Units assigned to them outside a project, and the project or Lab Unit their grant names inside one. Scope decides which tasks they reach, never whether they may act.
- Rule: Reviewing a discrepancy is not resolving it. Creating regrade work needs `data_manager`; adjudicating it needs `regrade_adjudicator`. Neither is conferred here.
- Relationship source: lab-unit assignment outside a project; project role grant at either scope inside one.
- Resource: grading_task (required).

## Domain: docs

### `docs.api.view`

- Rule: This action is deliberately public: View generated API documentation and OpenAPI/Swagger assets. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: documentation (not required).

## Domain: glaucoma_ai

### `glaucoma_ai.result.view`

- Rule: A user may view Glaucoma AI inference result, image, or thumbnail when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: glaucoma_ai_upload (required).

### `glaucoma_ai.upload.create`

- Rule: A user may create a Glaucoma AI upload and inference job when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: upload_selection (required).

### `glaucoma_ai.workspace.view`

- Rule: A user may view Glaucoma AI upload workspace and recent inference results when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: glaucoma_ai_upload (not required).

## Domain: grading

### `grading.arbitrator.submit`

- Rule: A user may submit an arbitration grade only when the user holds a grader role (`ophthalmologist` or `admin`) at user level and an active grading slot for that task's disease and lab unit permits arbitration.
- Rule: `admin` is not break-glass here. `ADMIN_GLOBAL` never authorizes a clinical submission; an administrator accepted as a grader in the current model must still hold the matching slot. D-50 separately records whether `admin` should count as a grader role at all.
- Rule: A slot permitting the resident or second-reader role does not permit arbitration.
- Relationship source: grading slot.
- Resource: grading task (required).

### `grading.grades.view`

- Rule: A grader may read their own grades on any task.
- Rule: A grader may also read every other grade on a task they have graded, including the second reader's, the arbitrator's and the AI grade allocated to that task, so they can see how their reading compared.
- Rule: Participation in the task is the relationship. No grading slot or project grant is re-checked, because grading the task already required one.
- Rule: A grader has no visibility of grades on tasks they did not grade.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: This action is the grader's own path to grades and is not how anyone else reaches them. A discrepancy reviewer, an analytics viewer, a collaborator and a regrade adjudicator each read grades through the surface built for their work, governed by its own rule. So the answer to "role X cannot see grades here" is never to widen this action; it is that role X reads them somewhere else, or should not.
- Relationship source: the actor's own participation in the task; admin-global scope.
- Resource: grade (required).

### `grading.resident.submit`

- Rule: A user may submit a resident grade only when the user holds a grader role (`ophthalmologist` or `admin`) at user level and an active grading slot for that task's disease and lab unit permits the resident role.
- Rule: `admin` is not break-glass here. `ADMIN_GLOBAL` never authorizes a clinical submission; an administrator accepted as a grader in the current model must still hold the matching slot. D-50 separately records whether `admin` should count as a grader role at all.
- Rule: A grading slot alone does not authorize grading, and the clinician role alone does not either. Both must hold.
- Rule: Grading of a project-owned task is additionally governed by grader allocation, not by a project role grant.
- Relationship source: grading slot.
- Resource: grading task (required).

### `grading.resident2.submit`

- Rule: A user may submit a second-reader grade only when the user holds a grader role (`ophthalmologist` or `admin`) at user level and an active grading slot for that task's disease and lab unit permits the second-reader role.
- Rule: `admin` is not break-glass here. `ADMIN_GLOBAL` never authorizes a clinical submission; an administrator accepted as a grader in the current model must still hold the matching slot. D-50 separately records whether `admin` should count as a grader role at all.
- Rule: A slot permitting the resident role does not permit the second-reader role; each slot authorizes only its own step of the workflow.
- Relationship source: grading slot.
- Resource: grading task (required).

## Domain: help

### `help.view`

- Rule: This action is deliberately public: View in-app help documentation. No authentication is required.
- Relationship source: none; the action is deliberately public.
- Resource: documentation (not required).

## Domain: inference

### `inference.wai.retry`

- Rule: A user may re-queue a failed WAI inference run when the user holds one of `admin`, `local_admin`, `data_manager`, within the lab units allocated to them.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Narrower than reading, because a retry spends an external API call.
- Relationship source: admin-global scope, lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: inference run (required).

### `inference.wai.rows`

- Rule: A user may read inference rows when they hold `fileUploader`, `verifier`, `data_manager`, `field_optometrist` or `field_ophthalmologist`, with `admin` as break-glass.
- Rule: Inference runs at capture, so its rows belong to the steps that capture and verify. Roles whose work begins at grading confer nothing here, and neither does `analytics_viewer`: these are records carrying identifiers, not the aggregate figures that role reads.
- Rule: This is stated rather than inherited from `inference.wai.summary`. One returns aggregates and the other returns records, which is a different disclosure, so the two role sets differ and a rule that delegated would have hidden that.
- Rule: This action returns rows carrying record identifiers and is therefore marked as showing them. Whether identifiers are actually rendered still depends on the reader's role through the masking layer; a non-PII role such as `analytics_viewer` sees them masked.
- Relationship source: lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: inference run (not required).

### `inference.wai.run`

- Rule: A user may request a WAI inference on a grading task when the user holds one of `admin`, `verifier`, `optometrist`, `field_optometrist`, `field_ophthalmologist`, within the lab units allocated to them.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: This applies on both sides of the project boundary. A classical task is reached through the actor's own lab units; a project task through a project role grant or an upload profile assignment for that project and lab.
- Relationship source: admin-global scope, lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: grading task (required).

### `inference.wai.summary`

- Rule: A user may view aggregate WAI inference statistics when the user holds one of `admin`, `local_admin`, `verifier`, `data_manager`, `analytics_viewer`, `optometrist`, `ophthalmologist`, `field_optometrist`, `field_ophthalmologist`.
- Rule: Outside a project the reach is the actor's own lab units. Inside one it is the lab units a project role grant or an upload profile assignment allocates to them.
- Rule: `admin` is unrestricted.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: admin-global scope, lab-unit assignment, hospital scope, project role grant, or upload profile assignment.
- Resource: inference run (not required).

## Domain: intra_rater

### `intra_rater.batch.create`

- Rule: A user may create intra-rater batches when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_batch (required).

### `intra_rater.batch.view`

- Rule: A user may view intra-rater batches and admin dashboards when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_batch (not required).

### `intra_rater.kpi.view`

- Rule: A user may view intra-rater KPI data when the user has one of `admin`, `data_manager`, `ophthalmologist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_task (not required).

### `intra_rater.task.submit`

- Rule: A user may submit an intra-rater grade when the user has one of `admin`, `ophthalmologist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_task (required).

### `intra_rater.task.view`

- Rule: A user may view assigned intra-rater tasks and image viewer when the user has one of `admin`, `data_manager`, `ophthalmologist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: intra_rater_task (not required).

## Domain: jobs

### `jobs.regenerate`

- Rule: A user may regenerate job-derived artifacts when the user has one of `admin`, `data_exporter`, `data_manager`, `dataset_creator`, `discrepancy_reviewer`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: job (required).

### `jobs.result.view`

- Rule: A user may view job result details and processing pages when the user has one of `admin`, `data_exporter`, `data_manager`, `dataset_creator`, `discrepancy_reviewer`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: job (required).

### `jobs.view`

- Rule: A user may view upload and processing jobs within scope when the user has one of `admin`, `data_exporter`, `data_manager`, `dataset_creator`, `discrepancy_reviewer`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: job (not required).

## Domain: media

### `media.image.view`

- Rule: A session user may view an image only when an accepted global role and classical scope, scoped project role, legacy project capability, collaborator relationship, exact grading-task eligibility, or exact direct-uploader relationship covers the resolved image.
- Rule: A valid signed-media credential may view only the exact resolved image UUID and signing hospital.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: classical scope, project authority, task eligibility, direct uploader, or signed-media token.
- Resource: resolved patient-media image.

### `media.metadata.process`

- Rule: Metadata extraction or refresh requires the same object authority before a filesystem or storage path is resolved.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Rule: Technical metadata - dimensions, format, bit depth, luminance, DPI - carries no identifier and is displayed alongside the image in the viewers, so it is readable by the roles in `MEDIA_IMAGE_ROLES`, matching image access exactly.
- Rule: The `exif_present` flag and the EXIF tags themselves are confined to the roles that read image identifiers - `MEDIA_PII_ROLES` together with `dataset_creator`. These are the verification and dataset-curation steps, which detect and correct identifiers; no other step needs either.
- Rule: Two audiences means two actions. `media.metadata.read` serves technical metadata to the roles in `MEDIA_IMAGE_ROLES`; a separate action serves `exif_present` and the raw tags to the identifier-reading roles. One action cannot carry both, because any role set wide enough for the first is too wide for the second.
- Rule: The EXIF tags themselves are patient identifiers. `include_raw` returns them and is confined to the roles that may read image identifiers, for diagnosis only. Every ingestion path strips EXIF, so a stored image should not carry any; where one does, that is a defect to remediate rather than a payload to serve.
- Resource: resolved patient-media image.

### `media.metadata.read`

- Rule: Image metadata is read only after the underlying image passes object authorization.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Rule: Technical metadata - dimensions, format, bit depth, luminance, DPI - carries no identifier and is displayed alongside the image in the viewers, so it is readable by the roles in `MEDIA_IMAGE_ROLES`, matching image access exactly.
- Rule: The `exif_present` flag and the EXIF tags themselves are confined to the roles that read image identifiers - `MEDIA_PII_ROLES` together with `dataset_creator`. These are the verification and dataset-curation steps, which detect and correct identifiers; no other step needs either.
- Rule: The EXIF tags themselves are patient identifiers. `include_raw` returns them and is confined to the roles that may read image identifiers, for diagnosis only. Every ingestion path strips EXIF, so a stored image should not carry any; where one does, that is a defect to remediate rather than a payload to serve.
- Resource: resolved patient-media image.

### `media.ocr_pii.process`

- Rule: PII OCR processing and manual overrides require object authorization before paths, prior records, or caches are accessed.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Rule: The relationship only decides *which images* are in reach. The role decides whether image identifiers may be read at all, and that set is capture, upload, verification and dataset curation: `admin`, `data_manager`, `dataset_creator`, `fileUploader`, `local_admin`, `optometrist`, `verifier`. A collaborator or a grading-task-eligible user therefore reaches the image and still cannot read an identifier off it.
- Resource: resolved patient-media image.

### `media.ocr_pii.read`

- Rule: PII OCR status, detections, and cached results are read only after the underlying image passes object authorization.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: image-capable classical or project authority, collaborator membership, or task eligibility.
- Rule: The relationship only decides *which images* are in reach. The role decides whether image identifiers may be read at all, and that set is capture, upload, verification and dataset curation: `admin`, `data_manager`, `dataset_creator`, `fileUploader`, `local_admin`, `optometrist`, `verifier`. A collaborator or a grading-task-eligible user therefore reaches the image and still cannot read an identifier off it.
- Resource: resolved patient-media image.

### `media.pdf.view`

- Rule: Source and generated report PDFs require document-capable classical or project authority; collaborator and grading-only relationships do not grant PDF access.
- Rule: A valid signed-media credential may view only the exact resolved source PDF UUID and signing hospital.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: document-capable classical scope, project authority, or signed-media token.
- Resource: resolved patient-media document.

### `media.thumbnail.view`

- Rule: Thumbnail access uses the same roles, the same relationships and the same identifier condition as `media.image.view`, and must not widen access based on variant availability.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: the same sources as `media.image.view`.
- Resource: resolved patient-media image.

## Domain: mobile

### `mobile.context.view`

- Rule: A user may read the authenticated mobile actor's own context and permissions only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: user (not required).

### `mobile.field.encounter.capture`

- Rule: A user may refresh, fetch, or re-fetch field encounter data for an assigned project only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority, or admin-global scope.
- Resource: project (required).

### `mobile.field.encounter.view`

- Rule: A user may read field encounters, images, and reports within an assigned project only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority, or admin-global scope.
- Resource: encounter (required).

### `mobile.field.inference.run`

- Rule: A user may trigger or retry inference for a field encounter only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority, or admin-global scope.
- Resource: encounter (required).

### `mobile.field.project.view`

- Rule: A user may list field projects the actor is assigned to only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row for that project.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority, or admin-global scope.
- Resource: project (not required).

### `mobile.session.revoke`

- Rule: A user may revoke one of the actor's own mobile sessions only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: mobile_session (required).

### `mobile.session.view`

- Rule: A user may list or read the actor's own mobile sessions only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: mobile_session (not required).

### `mobile.upload.create`

- Rule: A user may create a mobile upload and read its status only when the user has one of `admin`, `field_ophthalmologist`, `field_optometrist`, `ophthalmologist`, `optometrist` through an explicit project role grant or a legacy project capability row or an assigned upload profile that allows that project for that project.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority, upload profile assignment, or admin-global scope.
- Resource: upload_selection (required).

## Domain: notifications

### `notifications.update`

- Rule: A user may mark or update notifications for the authenticated user only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: notification (required).

### `notifications.view`

- Rule: A user may view notifications for the authenticated user only for their own record.
- Rule: `admin` is not break-glass here. The action is scoped to the actor's own record, and an administrator acting on another person's account does so through an explicit administrative action, which is attributable, rather than as that person.
- Relationship source: the actor owning the record.
- Resource: notification (not required).

## Domain: preprocess

### `preprocess.dashboard.view`

- Rule: A user may view preprocessing and anonymization dashboards when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: image (not required).

### `preprocess.image.update`

- Rule: A user may anonymize, restore, or override PII on scoped images when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: image (required).

## Domain: projects

### `project.access.manage`

- Rule: A user may grant or revoke project role assignments for other users only when the user holds `project_admin` on that project, at either project or lab-unit scope.
- Rule: The actor may only write authority at or below the scope of their own grant. A project-scoped access manager may write at any scope in the project; a lab-unit-scoped access manager may write only at that Lab Unit, and may neither create a project-scoped grant nor reach another Lab Unit.
- Rule: An actor may never grant themselves authority they do not already hold, at any scope.
- Rule: Only operational roles may be granted this way. Governance roles are appointed by a System Admin and are never delegable.
- Rule: Lab-unit assignment outside a project grant never authorizes this action, and hospital scope is retired.
- Rule: Whether a project centralises access management in one project-wide manager or decentralises it to a manager per Lab Unit is a matter of the project's scale. Both are supported by the same containment rule, and neither widens what any one manager may do.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority, under a delegation constraint on the actor's own grant scope.
- Resource: project (required); Lab Unit (required when the actor's grant is lab-unit scoped).

### `project.encountersets.browse`

- Rule: A user may browse EncounterSets belonging to a project, without patient identifiers only when the user has one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` through an explicit project role grant or a legacy project capability row for that project.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority.
- Resource: encounter_set (required).

### `project.encountersets.browse_pii`

- Rule: A user may browse project EncounterSets including patient identifiers only when the user holds one of `verifier` or `optometrist` on that project through a project role grant, or reaches the project through an upload profile assignment as `fileUploader`, `pregarded_uploader`, `data_manager` or `local_admin`. `admin` is break-glass.
- Rule: Identifiers belong to capture, upload and verification. Every role whose work begins at grading confers nothing here - grading, discrepancy review, regrade adjudication, curation, export - and neither do the governance roles, whose oversight explicitly excludes patient identifiers.
- Rule: This narrows only `project.encountersets.browse_pii`. Every role that may browse keeps browsing through `project.encountersets.browse`, with identifiers masked.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Relationship source: project authority.
- Resource: encounter_set (required).

### `project.upload.direct_image`

- Rule: A user may upload direct images into a project only when the user holds one of `fileUploader`, `pregarded_uploader`, `optometrist`, `data_manager`, `local_admin`, `verifier`, `field_optometrist`, `field_ophthalmologist` and an active upload profile assignment covers that project.
- Rule: The profile decides which kinds of upload are permitted; the upload grant decides which Lab Units. Both bounds must hold, and the role alone authorizes nothing.
- Rule: A project role grant does not authorize uploading. Browsing a project is not ingesting into it, so `collaborator`, `analytics_viewer` and the governance roles confer nothing here.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.encounter_set`

- Rule: A user may upload EncounterSet packages into a project only when the user holds one of `fileUploader`, `pregarded_uploader`, `optometrist`, `data_manager`, `local_admin`, `verifier`, `field_optometrist`, `field_ophthalmologist` and an active upload profile assignment covers that project.
- Rule: The profile decides which kinds of upload are permitted; the upload grant decides which Lab Units. Both bounds must hold, and the role alone authorizes nothing.
- Rule: A project role grant does not authorize uploading. Browsing a project is not ingesting into it, so `collaborator`, `analytics_viewer` and the governance roles confer nothing here.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.pregraded`

- Rule: A user may upload pre-graded image sets into a project only when the user holds `pregarded_uploader` and an active upload profile assignment covers that project.
- Rule: `fileUploader` does not confer this. Pre-graded ingestion identifies the AI model whose grades these are and maps the source sheet onto the grade catalogue; that is technical work the generic uploading role does not cover.
- Rule: The profile decides which kinds of upload are permitted; the upload grant decides which Lab Units. Both bounds must hold, and the role alone authorizes nothing.
- Rule: A project role grant does not authorize uploading. Browsing a project is not ingesting into it, so `collaborator`, `analytics_viewer` and the governance roles confer nothing here.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.remidio`

- Rule: A user may upload Remidio ZIP packages into a project only when the user holds one of `fileUploader`, `pregarded_uploader`, `optometrist`, `data_manager`, `local_admin`, `verifier`, `field_optometrist`, `field_ophthalmologist` and an active upload profile assignment covers that project.
- Rule: The profile decides which kinds of upload are permitted; the upload grant decides which Lab Units. Both bounds must hold, and the role alone authorizes nothing.
- Rule: A project role grant does not authorize uploading. Browsing a project is not ingesting into it, so `collaborator`, `analytics_viewer` and the governance roles confer nothing here.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority.
- Resource: project (required).

### `project.upload.remidio_api_sync`

- Rule: A user may run Remidio API synchronisation for a project only when the user holds one of `fileUploader`, `pregarded_uploader`, `optometrist`, `data_manager`, `local_admin`, `verifier`, `field_optometrist`, `field_ophthalmologist` and an active upload profile assignment covers that project.
- Rule: For a manual sync the profile must permit the Remidio API sync kind, and its assignment must cover every active route Lab Unit the requested project sync will use. The dashboard's eligible-project list confers nothing on the later mutation.
- Rule: The user who started a manual project-sync job may pause, resume or cancel it only while that same user still holds this action; another eligible uploader may not take over the job. `admin` is break-glass.
- Rule: A scheduled prospective sync has no user. It is admitted by the active stored prospective-sync, routing-profile, source-rule and project-binding configuration, and the worker may process only the exact project and routes selected by that configuration.
- Rule: The user id carried by a manual worker job is attribution, not delegated authority. An interactive resume or retry is authorized again before enqueue.
- Rule: A project role grant does not authorize uploading. Browsing a project is not ingesting into it, so `collaborator`, `analytics_viewer` and the governance roles confer nothing here.
- Rule: Hospital scope or lab-unit assignment alone never grants this action; project rows require an explicit project relationship.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority.
- Resource: project (required).

### `project.uploaders.manage`

- Rule: A user may assign upload profiles and uploader access within a project only when the user holds `project_admin` on that project, at either project or lab-unit scope.
- Rule: The same containment applies as for `project.access.manage`: a lab-unit-scoped access manager may bind uploaders only into their own Lab Unit, and the requested Lab Units are checked against the actor's scope, not merely against the project's configuration.
- Rule: Creating and configuring the upload profiles themselves is reserved to a System Admin. This action only assigns a user to a profile that already exists.
- Rule: Lab-unit assignment outside a project grant never authorizes this action, and hospital scope on a project grant is retired.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project authority, under a delegation constraint on the actor's own grant scope.
- Resource: project (required).

### `project.view`

- Rule: A user may view a project overview and its configuration summary when the user holds one of `analytics_viewer`, `collaborator`, `data_exporter`, `dataset_creator`, `discrepancy_reviewer`, `ophthalmologist`, `optometrist`, `project_admin`, `project_pi`, `regrade_adjudicator`, `site_pi`, `verifier` on that project through a role grant, **or** one of `fileUploader`, `pregarded_uploader`, `optometrist`, `data_manager`, `local_admin`, `verifier`, `field_optometrist`, `field_ophthalmologist` through an upload profile assignment on that project.
- Rule: This action is an ordinary gate: any explicit project relationship, at project or lab-unit scope, admits the viewer to the overview page. Scope does not bear on admission. What the page then shows is decided by the other actions it draws on, each filtered by the viewer's scope. What the page displays is still decided per action (browse, upload, manage access, run WAI, ...), so a user with only an upload-profile assignment sees an overview limited to their upload cards.
- Rule: Hospital scope or lab-unit assignment alone (with no project relationship at all) never grants this action.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project role grant, project collaborator grant, legacy project-capability grant, or an upload profile assignment.
- Resource: project (required).

### `project.wai.results`

- Rule: A user may view Wadhwani AI inference results for a project when the user holds one of `optometrist`, `ophthalmologist`, `verifier`, `data_manager`, `analytics_viewer`, `project_admin`, `project_pi`, `site_pi`, `field_optometrist`, `field_ophthalmologist` on that project through a role grant.
- Rule: The grant's own scope decides how much of the project is reached. A lab-scoped grant reaches that lab's inference results; a project-wide grant reaches the project. This is a filter, not a gate: partial authority confers partial reach rather than nothing.
- Rule: Hospital scope or lab-unit assignment alone never grants this action on project data.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project role grant, or an upload profile assignment covering the same (project, lab unit).
- Resource: project (required).

### `project.wai.run`

- Rule: A user may trigger Wadhwani AI inference for project encounters when the user holds one of `optometrist`, `verifier`, `field_optometrist`, `field_ophthalmologist` on that project through a role grant.
- Rule: The grant's own scope decides which encounters. A lab-scoped grant authorizes inference in that lab only.
- Rule: Hospital scope or lab-unit assignment alone never grants this action on project data.
- Rule: `admin` is break-glass here as everywhere else.
- Relationship source: project role grant, or an upload profile assignment covering the same (project, lab unit).
- Resource: project (required).

## Remote inference (WAI)

Inference output is read at the verification stage, before grading, which is
why it is registered under `inference.` rather than `analytics.` and why the
row-level action is allowed to show patient identifiers.

Reach follows lab-unit allocation on both sides of the project boundary, and
additionally follows upload profile assignments. That last part is load-bearing:
an automated Remidio API pull is created by a schedule, not a person, so it
carries no uploading user, and the WAI inferences that run automatically on
those pulls inherit the same gap. Field staff therefore reach them through the
lab units their upload profiles cover, never through ownership. Because the
reach is the lab unit rather than the profile, a project running a manual
profile alongside an automated one still resolves correctly: an assignment to
either profile in lab L reaches everything in lab L, whichever profile ingested
it. Ownership is offered as a filter over that set; it is never the condition,
because conditioning on it would hide exactly the automated rows field staff
need.

## Domain: public

### `public.view`

- Rule: This action is deliberately public: the public application landing surface and the public analytics page and its aggregate APIs. No authentication is required. Login, help and documentation use their own explicitly public actions.
- Rule: Public analytics may expose only explicitly approved system-wide totals, trends and aggregates. It may not expose patient rows, identifiers, exports or project clinical-result drill-downs; authenticated KPI actions remain separate.
- Rule: A route is public only because this policy names it, never because its URL uses `/analytics`, `/help`, `/docs` or another allowlisted prefix.
- Relationship source: none; the action is deliberately public.
- Resource: public_page (not required).

## Domain: reports

### `reports.view`

- Rule: A user may view scoped DR and glaucoma report data by UUID when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: report (required).

## Domain: screenings

### `screenings.delete`

- Rule: A user may delete screening records or reports when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: encounter (required).

### `screenings.reprocess`

- Rule: A user may reprocess screening PDF data when the user has one of `admin`, `data_manager` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: encounter (required).

### `screenings.view`

- Rule: A user may view screening records and details when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: encounter (not required).

## Domain: search

### `search.view`

- Rule: A user may search scoped tasks, images, and image details when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: search_result (not required).

## Domain: tasks

### `tasks.view`

- Rule: A user may view task dashboards, pending tasks, all tasks and task details when they hold `admin`, or hold `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist` or `optometrist`.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Each acts within their defined scope - the Lab Units assigned to them outside a project, and the project or Lab Unit their grant names inside one.
- Rule: A project's governance roles - `project_pi`, `site_pi`, `project_admin` - and `collaborator` also browse that project's tasks. Browsing is what feeds regrade and intra-rater creation, and oversight cannot oversee work it cannot see.
- Rule: Browsing a task is not grading it. Grading is reached only through a grading slot and, for project-owned tasks, grader allocation.
- Relationship source: admin-global scope; lab-unit assignment outside a project; project role grant at either scope inside one.
- Resource: grading_task (not required).

### `tasks.viewer.view`

- Rule: A user may view task image viewer assets when they hold `admin`, or hold `data_manager`, `fileUploader`, `local_admin`, `ophthalmologist` or `optometrist`.
- Rule: `admin` is break-glass here as everywhere else.
- Rule: Each acts within their defined scope - the Lab Units assigned to them outside a project, and the project or Lab Unit their grant names inside one.
- Rule: A project's governance roles - `project_pi`, `site_pi`, `project_admin` - and `collaborator` also browse that project's tasks. Browsing is what feeds regrade and intra-rater creation, and oversight cannot oversee work it cannot see.
- Rule: Browsing a task is not grading it. Grading is reached only through a grading slot and, for project-owned tasks, grader allocation.
- Relationship source: admin-global scope; lab-unit assignment outside a project; project role grant at either scope inside one.
- Resource: image (required).

## Domain: upload

### `upload.direct.create`

- Rule: The ordinary path permits a direct image upload when the user has the `fileUploader` role and an active upload profile assignment matching the selected project, lab unit, disease, camera, area, and upload kind.
- Rule: Direct-image upload creation must tag the created direct image with the same project that was authorized through the upload profile.
- Rule: A duplicate direct-image creation attempt may create only job bookkeeping for the attempt and, if the current upload profile enables Wadhwani AI, canonical-image AI task/run/grade records needed for that current model. It must not create direct-image verification records or verification work.
- Rule: Alternatively, `admin` is break-glass through `ADMIN_GLOBAL` without an uploader role or assignment. The selected profile must still be active and match every requested target and clinical dimension, and the decision must be recorded. Neither holds in code - the action takes `UPLOAD_PROFILE` alone (D-39), and no resolver validates a profile the actor is not assigned to (D-43).
- Relationship source: upload profile assignment, or admin-global scope together with a selected active profile.
- Resource: `upload_selection`.

### `upload.direct.edit_image`

- Rule: A user may edit, anonymise, or restore a direct image upload when the user has one of `admin`, `data_manager`, `fileUploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: direct_image_upload (required).

### `upload.direct.view`

- Rule: A user may view the direct upload dashboard and upload job status when the user has one of `admin`, `data_manager`, `fileUploader`, `pregarded_uploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: direct_image_upload (not required).

### `upload.pregraded.create`

- Rule: The ordinary path permits a pre-graded image set and its grades when the user has `pregarded_uploader` and the selected upload profile is active, assigned to the user, and matches the selected project, lab unit, and upload kind.
- Rule: `fileUploader` does not confer this. Pre-graded ingestion identifies the AI model whose grades these are and maps the source sheet onto the grade catalogue; that is technical work the generic uploading role does not cover.
- Rule: Alternatively, `admin` is break-glass through `ADMIN_GLOBAL` without an uploader role or assignment. The selected profile must still be active and match every requested target and clinical dimension, and the decision must be recorded. Neither holds in code - the action takes `UPLOAD_PROFILE` alone (D-39), and no resolver validates a profile the actor is not assigned to (D-43).
- Relationship source: upload profile assignment, or admin-global scope together with a selected active profile.
- Resource: upload_selection (required).

### `upload.zip.create`

- Rule: The ordinary path permits a Remidio or EncounterSet ZIP package when the user has `fileUploader` and the selected upload profile is active, assigned to the user, and matches the selected project, lab unit, and upload kind.
- Rule: Alternatively, `admin` is break-glass through `ADMIN_GLOBAL` without an uploader role or assignment. The selected profile must still be active and match every requested target and clinical dimension, and the decision must be recorded. Neither holds in code - the action takes `UPLOAD_PROFILE` alone (D-39), and no resolver validates a profile the actor is not assigned to (D-43).
- Relationship source: upload profile assignment, or admin-global scope together with a selected active profile.
- Resource: upload_selection (required).

### `upload.zip.view`

- Rule: A user may list previously uploaded ZIP packages when the user has one of `admin`, `data_manager`, `fileUploader`, `pregarded_uploader`, `local_admin`, `optometrist` and admin-global scope, hospital scope, or an explicit lab-unit assignment covers the resource.
- Relationship source: classical scope.
- Resource: uploaded_zip (not required).

## Domain: verification

### `verification.direct.update`

- Rule: A user may update direct-image verification metadata or image tags only when the user has one of `verifier` or `admin` and the direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

### `verification.direct.view`

- Rule: A user may view direct-image verification pages only when the user has one of `verifier` or `admin` and the direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

### `verification.encounter_set.update`

- Rule: A user may verify an EncounterSet encounter only when they hold `verifier`, or `admin` as break-glass. No uploading or administrative role confers it.
- Rule: A `verifier` acts within their defined scope - the Lab Units assigned to them outside a project, and the project or Lab Unit their grant names inside one. Scope decides which encounters they reach, never whether they may act.
- Rule: For a project-owned encounter the relationship must be a project role grant. Lab-unit assignment alone never authorizes verification of project data, and the legacy project capability row confers nothing.
- Relationship source: classical scope for unowned encounters; project authority for owned ones.
- Resource: encounter (required).

### `verification.pregraded.update`

- Rule: A user may update pregraded direct-image verification metadata or tags only when the user has one of `verifier` or `admin` and the pregraded direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

### `verification.pregraded.view`

- Rule: A user may view pregraded direct-image verification pages only when the user has one of `verifier` or `admin` and the pregraded direct image is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `direct_image_upload`.

### `verification.remidio.update`

- Rule: A user may update Remidio encounter report or image verification state only when the user has one of `verifier` or `admin` and the encounter is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `encounter`.

### `verification.remidio.view`

- Rule: A user may view Remidio verification queues and details only when the user has one of `verifier` or `admin` and the encounter is covered by admin-global scope, hospital scope, or explicit lab-unit assignment.
- Relationship source: `admin_global`, `hospital_scope`, or `lab_unit_assignment`.
- Resource: `encounter`.

## Migration Gate

Before wiring a route to ReBAC:

- Add or confirm the action in `authz/actions/*.toml`.
- Add a simple sentence rule in this document.
- Add or confirm the executable policy in `authz/policies.py`.
- Add tests for role failure and relationship failure.
- Then wire the route or service to the action.
