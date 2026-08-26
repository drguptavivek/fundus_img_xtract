---
title: Project Authorization Matrix
authority: docs/policy/authorizations.md
summary: Which role reaches which project action, and at what grant scope, as the policy decides it.
---

# Project Authorization Matrix

Which role reaches which project action, and at what grant scope. This is the policy as
decided: what must be true. [`authorizations.md`](authorizations.md) carries the rule behind
every cell and is the authority; where the two disagree, it wins.

`20 roles` · `16 project actions` · `two grant scopes` · governance and operational drawn separately

## The four rules the grid is built from

**A grant's scope is authoritative.** A project role grant carries exactly one scope —
`project`, meaning the whole project across every Lab Unit configured for it, or `lab_unit`,
meaning one of them. No role is promoted beyond the scope stored on its grant. Hospital scope
on a project role grant is retired; classical hospital scope, which `local_admin` uses outside
any project, is untouched.

**Scope filters rows; it decides the action only where the effect spans the project.** Most
actions are reached by a tuple on either object, and the object the tuple sits on then
determines which rows come back — that narrowing is enforcement, not a second decision. Where
the effect cannot carry a scope of its own, only a tuple on the project satisfies it. A dataset
is the clearest case: one drawn from part of a project is not a smaller project dataset, it is
not one.

**Authority is delegated downward or not at all.** An actor may write tuples only on objects
its own tuples already reach. That single rule lets a small project keep one project-wide
access manager and a large multi-site one appoint an access manager per site, without the
policy differing between them.

**Each step's authority stops where the next step begins.** Uploading is not verifying,
assembling a dataset is not releasing it, and creating regrade work is not adjudicating it.
Each cut is a deliberate one, and each is explained below.

## Break-glass

`admin` reaches every action through `ADMIN_GLOBAL`, without a personal assignment. It is the
exception path, not a second ordinary one, and it relieves exactly one requirement: that the
actor hold an assignment. It waives nothing else — a break-glass upload still needs the selected
profile to be active and configured for the target, the created records still carry the
authorized project, and because the exception *writes* patient records rather than reading them,
the decision is recorded.

Two classes sit outside it, both deliberately. An action scoped to the actor's own record — a
password, a session, a notification, a viewer preference — is never reachable by break-glass: an
administrator acting on another person's account does so through an explicit administrative
action, which is attributable, rather than as that person. And a grading submission requires the
grading slot itself, because the `admin` role does not stand in for the clinician role.

## Governance

Governance roles govern the project — who is on it, and oversight of what it produces. Only a
System Admin may grant one; no access manager may delegate governance at any scope.

**Oversight observes and does not act.** It grades nothing, verifies nothing, adjudicates nothing
and ingests nothing. Those columns are omitted from this grid rather than drawn as a wall of
dashes — no governance role holds any of them, at any scope.

### Columns

| Column | Covers | Grant source |
|:---|:---|:---|
| `view` | the project overview | project grant · upload profile |
| `browse` | encounter sets, no identifiers | project grant |
| `record ids` | the patient's details on the encounter | project grant |
| `image ids` | OCR detections, EXIF flag and tags | project grant |
| `access.manage` | delegate operational roles | project grant · contained |
| `uploaders.manage` | bind uploaders to profiles | project grant · contained |
| `curation.view` | browse datasets | classical · project |
| `wai.results` | read results | project grant |
| `kpi.aggregate` | counts and distributions | classical · project |
| `kpi.rows` | the line list behind them | classical · project |

### Grid

| Role | Grant scope | `view` | `browse` | `record ids` | `image ids` | `access.manage` | `uploaders.manage` | `curation.view` | `wai.results` | `kpi.aggregate` | `kpi.rows` |
|:---|:---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `project_pi` | project | ● | ● | — | — | — | — | ● | ● | ● | ● |
| `site_pi` | lab_unit | ● | ● | — | — | — | — | ● | ● | ● | ● |
| `project_admin` | project · lab_unit | ● | ● | — | — | ◈ | ◈ | ● | ● | ● | ● |

`project_pi` is granted at project scope only. `site_pi` at lab-unit scope only: it may hold
several Lab Units within a project, because a site is not always one Lab Unit, but it may never
hold the project itself. That invariant is why `site_pi` stays a distinct role although its
action set matches `project_pi`'s exactly — a `project_pi` grant created at lab-unit scope by
mistake would draw no objection, whereas a `site_pi` grant at project scope is invalid by
definition and is rejected on write.

Being lab-unit-scoped, `site_pi` is also subject to the project's site settings: it reads and
exports its site's own encounters and data regardless, and reaches its graders' readings only
where the project has enabled site grade export and it holds `data_exporter`.

## Operational

Operational roles do the project's work. A `project_admin` may delegate them within its own
grant scope, and each is a filter over the rows its grant covers.

### Columns

| Column | Covers | Grant source |
|:---|:---|:---|
| `view` | the project overview | project grant · upload profile |
| `browse` | encounter sets, no identifiers | project grant |
| `record ids` | the patient's details on the encounter | project grant |
| `image ids` | OCR detections, EXIF flag and tags | project grant |
| `access.manage` | delegate operational roles | project grant · contained |
| `uploaders.manage` | bind uploaders to profiles | project grant · contained |
| `upload.*` | create an upload | profile decides the kind, grant the Lab Unit |
| `verification.*` | judge data fit to grade | project grant |
| `wai.run` | run inference | project grant |
| `wai.results` | read results | project grant |
| `curation.view` | browse datasets | classical · project |
| `curation.update` | curate, finalise, delete | project only |
| `export.*` | create and download an export | project only |
| `share.manage` | mint and administer shares | project only |
| `kpi.aggregate` | counts and distributions | classical · project |
| `kpi.rows` | the line list behind them | classical · project |

### Grid

| Role | Grant scope | `view` | `browse` | `record ids` | `image ids` | `access.manage` | `uploaders.manage` | `upload.*` | `verification.*` | `wai.run` | `wai.results` | `curation.view` | `curation.update` | `export.*` | `share.manage` | `kpi.aggregate` | `kpi.rows` |
|:---|:---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Operational** | |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| `collaborator` | project · lab_unit | ● | ● | — | — | — | — | — | — | — | — | — | — | — | — | ● | ● |
| `verifier` | project · lab_unit | ● | ● | ● | ● | — | — | — | ● | — | ● | — | — | — | — | — | — |
| `ophthalmologist` | project · lab_unit | ● | ● | — | — | — | — | — | — | — | ● | — | — | — | — | ● | ● |
| `optometrist` | project · lab_unit | ● | ● | ● | ● | — | — | ● | — | ● | ● | — | — | — | — | — | — |
| `analytics_viewer` | project · lab_unit | ● | ● | — | — | — | — | — | — | — | ● | — | — | — | — | ● | ● |
| `dataset_creator` | project · lab_unit | ● | ● | — | ● | — | — | — | — | — | — | ● | ⊕⚙ | — | — | — | — |
| `data_exporter` | project · lab_unit | ● | ● | — | — | — | — | — | — | — | — | ● | — | ⊕⚙ | ⊕⚙ | — | — |
| `pii_exporter` | project · lab_unit | — | — | — | — | — | — | — | — | — | — | — | — | ✚ | ✚ | — | — |
| `discrepancy_reviewer` | project · lab_unit | ● | ● | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `regrade_adjudicator` | project · lab_unit | ● | ● | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| **Capture** | |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| `fileUploader` | lab_unit | ● | — | ● | ● | — | — | ● | — | — | ● | — | — | — | — | — | — |
| `pregarded_uploader` | lab_unit | ● | — | ● | ● | — | — | ● | — | — | ● | — | — | — | — | — | — |
| `field_optometrist` | lab_unit | ● | — | ● | ● | — | — | ● | — | ● | ● | — | — | — | — | — | — |
| `field_ophthalmologist` | lab_unit | ● | — | ● | ● | — | — | ● | — | ● | ● | — | — | — | — | — | — |
| **Classical** | |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| `data_manager` | lab_unit | ● | — | — | — | — | — | — | — | ● | ● | — | — | — | — | ● | ● |
| `local_admin` | hospital | ● | — | — | — | — | — | — | — | — | — | — | — | — | — | ● | ● |

| Mark | Meaning |
|:---:|:---|
| ● | **Granted.** The grant's scope then filters which rows are reached. |
| ⊕ | **Project scope only.** The effect spans the project, so a Lab Unit grant confers nothing, however many are held. |
| ◈ | **Contained.** Tuples may be written only on objects the actor's own tuples already reach, never a broader one. |
| ⚙ | **Site setting applies.** Withheld from a lab-unit-scoped holder until the project enables it for that Lab Unit. Off by default. |
| ✚ | **Additive.** Held alongside the role that authorizes the release, never instead of it. |
| — | **Not granted** at any scope. |

## Why the grid cuts where it does

### Governance is appointed; it observes and does not act

Only a System Admin grants `project_pi`, `site_pi` or `project_admin`. No access manager may
delegate governance at any scope. Oversight grades nothing, verifies nothing, adjudicates
nothing and ingests nothing — hence the empty Ingest and Verify columns across all three.

`project_pi` is granted at project scope only. `site_pi` at lab-unit scope only: it may hold
several Lab Units within a project, because a site is not always one Lab Unit, but it may never
hold the project itself. That invariant is why `site_pi` stays a distinct role although its
action set matches `project_pi`'s exactly — a `project_pi` grant created at lab-unit scope by
mistake would draw no objection, whereas a `site_pi` grant at project scope is invalid by
definition and is rejected on write.

### Ingesting and verifying are different work

An uploader may be a non-technical operator. Deciding whether captured data is fit to become
gradable work needs someone technical, which is why `verifier` exists and why the judgement was
moved off `optometrist`.

**`verifier` is the only role that authorizes verification**, with `admin` as break-glass. Not
`fileUploader`, not `data_manager`, not `local_admin`. Each of those held it by inheritance
rather than by decision, and every additional holder is ambiguity about who is accountable for
the judgement. A user who should verify is granted `verifier`.

### Assembling a dataset and releasing it are different work

`dataset_creator` assembles: curates, updates, finalises, deletes. `data_exporter` releases:
exports and administers shares. `dataset_creator` holds no release action at all.

The cut is egress. Assembling keeps patient data inside the system; exporting a file or minting
a share link takes it out, which is a different risk and belongs to a different holder — the
same reasoning that separated verification from uploading. Only a finalised dataset may be
released, and release carries the project's whole scope, so a lab-unit grant confers nothing.

Separating the work does not separate the people: one person may hold both roles. The control
is that each action names the role it needs, so a holder of only one cannot reach past it.

### Uploading is bounded twice

The upload profile decides the kind of upload; the grant decides the Lab Unit. Holding `admin`,
`local_admin`, `data_manager` or hospital scope is not itself upload access — which is why the
Ingest column is empty for the classical roles. `pregarded_uploader` is a separate role because
the work is technical rather than clerical: identifying the AI model whose grades these are, and
mapping the source sheet's values onto the standard grade catalogue. It asserts findings rather
than only capturing images, and the generic uploading role does not confer it.

### Break-glass is a relationship, not a role

`admin` reaches every action through `ADMIN_GLOBAL`, without a personal assignment. It is the
exception path, not a second ordinary one, and it relieves exactly one requirement: that the
actor hold an assignment. It waives nothing else — a break-glass upload still needs the selected
profile to be active and configured for the target, the created records still carry the
authorized project, and because the exception *writes* patient records rather than reading them,
the decision is recorded.

Two classes sit outside it, both deliberately. An action scoped to the actor's own record — a
password, a session, a notification, a viewer preference — is never reachable by break-glass: an
administrator acting on another person's account does so through an explicit administrative
action, which is attributable, rather than as that person. And a grading submission requires the
grading slot itself, because the `admin` role does not stand in for the clinician role.

### Grading is not on this grid

Grading a project-owned task is governed by grader allocation, not by a project role grant, so
it has no column here. Two things must hold and neither substitutes for the other: the
user-level qualification (`ophthalmologist`), and an active grading slot for that task's disease
and Lab Unit. A slot alone does not authorize grading; the clinical role alone does not either.

## Patient identifiers

Three different things are called patient identifiers, and they are governed separately. Two of
them are columns above; the third follows the second.

**Record identifiers** — the patient's details held on the encounter. Reading them is disclosure
and nothing else. They belong to **capture, upload and verification**, which need to know which
patient an encounter is. Grading, discrepancy review, regrade adjudication, intra-rater work,
analytics, dataset curation and export never need them.

**Image identifiers** — details burnt into the image, found by OCR. Seeing them is how they get
removed. They belong to capture, upload, verification **and dataset curation** — the steps that
correct an image before it moves on. A curator filters to the images OCR flagged, opens the
detections to see what and where, and corrects them. It is the last chance to catch a leak
before data leaves the system.

So dataset curation reads image identifiers and not record identifiers: it needs to know an
image carries a name in order to crop it out, and never needs to know whose name it is.

**Embedded file identifiers** — the camera's own EXIF tags. They differ from the other two in a
way that makes the rule stricter, not looser: **removing them does not require reading them.**
Burnt-in text must be inspected before it can be cropped, so the correcting steps must see it.
EXIF can be stripped without anyone looking, so no workflow step needs its contents. Every
ingestion path strips it. Whether a stored image still carries any is reported as a flag,
`exif_present`, which discloses no patient detail but is still confined to the roles that may
read image identifiers: it says an image is unclean, which is only actionable by whoever may
clean it. The tags themselves are readable only by those roles, and only for diagnosing why a
strip failed.

This is a property of the action, not of the actor's roles. Deciding it from roles alone unmasks
a grader who also happens to upload, on the grading screen itself. An action that has not been
classified masks by default.

`pii_exporter` is the one role that lets an identifier leave the system. Every other role that
may read one may read it only in place. It is held alongside the role that authorizes the
release itself, never instead of it, which is why its row is additive rather than a set of
grants of its own.

## What each site may do

Three settings sit on the binding between a project and one of its Lab Units, so a study may
trust one site with work it withholds from another. Each defaults to **off**, and each governs
every lab-unit-scoped holder there — operational roles and `site_pi` alike. The same person
holding grants at two Lab Units may export grades at one and not the other. A project-wide
holder is unaffected by any of them.

| Setting | Governs | Also requires |
|:---|:---|:---|
| `sites_can_export_grades` | Export of the readings human graders produced | `data_exporter` |
| `sites_can_create_datasets` | Dataset curation and finalisation | `dataset_creator` |
| `sites_can_share_datasets` | Dataset sharing and release | `dataset_creator` |

A site always exports its own encounters, images and captured data — that is its own record and
no setting withholds it. What is withheld by default is the **grades**: the project's clinical
output rather than the site's account of what it captured. A site takes those out only when
`sites_can_export_grades` is on **and** the holder has `data_exporter`. Neither alone suffices,
and a setting that is off narrows nothing except the work named in the table.

## Reserved to a System Admin

Project setup carries consequences across the whole project and is never delegable to
`project_pi`, `site_pi` or `project_admin` at any scope.

- Upload profile **definitions** — distinct from assigning a user to an existing profile, which is `uploaders.manage`
- Grading schemes and grading profiles
- WAI autorun configuration
- Remidio API routing and connection bindings
- Which Lab Units a project spans

## Roles whose scope is classical

`local_admin` administers one hospital and the Lab Units within it, and may hold several — it
holds one relation per hospital and reaches exactly those. This is why the hospital cannot stay
a column on the user record: a column holds one value, and the relation is what allows several.
`current_user.hospital_id` is never an authorization rule.

`data_manager` administers the work without performing it: it creates and reassigns regrade
tasks and intra-rater batches, and runs inference retrospectively. Running inference at capture
is different work from re-running it later, which is why the clinic and field roles hold
`wai.run` too.
