---
title: Authorization In Plain Language
authority: docs/policy/authorizations.md
summary: Who is allowed to do what, at each step of the work, in plain English.
---

# Authorization In Plain Language

Who is allowed to do what, at each step of the work. No jargon. The formal version lives in
[`authorizations.md`](authorizations.md), and where the two differ, that one is right.

## Roles and assignments work together

A **role** says what kind of work somebody may do. An **assignment** says where they may do it.

For ordinary scoped work, neither is enough on its own. Someone can hold the uploading role and
be unable to upload anywhere, because nothing has said which site. Someone can be assigned to a
site and be unable to do anything there, because they hold no role. The system normally asks
both questions together: is this the person's kind of work, and has this place or object been
assigned to them?

There are explicit alternatives. Public pages need neither. Work on your own account follows
the relationship to yourself. A signed link reaches only the exact object it names. The system
administrator's emergency relationship is described below. These are named paths through the
same policy, not shortcuts around it.

## Two worlds

Work happens either **inside a project** or **outside one**, and the same person may do both.

Outside a project, reach comes from the hospital or the sites somebody is assigned to. This is
where most day-to-day work still lives.

Inside a project, reach comes from a grant the project gave them. That grant covers either the
whole project, or one of its sites. Nothing promotes anybody beyond what their grant says.

Being assigned to a site never reaches a project's data. If a project owns the record, it takes
the project's say-so.

## Opening a screen and doing the work

Opening a screen, seeing its contents and changing something are separate questions.

First, the page checks whether the person has any relevant reach in the requested project or
outside-project setting. The page may then ask the server which projects, sites, profiles,
tasks, datasets or other choices this person can currently use. Only those choices come back;
the browser is never given a larger list and asked to hide the rest.

That list helps build the screen, but it is not permission to act later. When somebody submits
an upload, assigns a role, settles a disagreement, changes a dataset or performs another
operation, the server loads the exact objects again and authorizes that exact request. A stale
page, an edited form or a direct API call therefore confers nothing.

A page made of several panels does not get one oversized permission. A project dashboard may
admit somebody to the overview while its upload, analytics, grading, dataset and access panels
each ask their own question and return only their own authorized data.

## Permission is checked again as work moves

Authority is not frozen when a page, task or job is first opened. The server checks the current
state again when the action is submitted.

A verifier cannot reopen or retag an encounter once downstream grading makes that unsafe. A
grader still needs the correct live task state, grading slot and project allocation at submission,
and cannot submit the same step twice. Regrade, intra-rater and ad hoc work likewise checks that
the source is still eligible and the assignment is still current.

A stale browser tab, an old eligibility response and a queued-but-not-yet-run request therefore
carry no authority of their own.

## Getting pictures in

**Outside a project** an ordinary uploader may use the ordinary upload formats — direct images
and camera ZIPs — but only into the sites they've been assigned to. Broad in what among those
ordinary formats, narrow in where they may be sent. Pre-graded ingestion remains the separate
exception described below.

**Inside a project** it's narrow in both. Their upload profile decides what kind they may send.
Their assignment decides which site it goes to. A profile never names a site and an assignment
never names a kind, so both have to be present. Holding the right profile with no assignment
covering that site means uploading nothing there.

A pre-graded set is different in both worlds. Loading one means saying which AI model produced
the readings and matching that spreadsheet's wording to our own list of grades. That's a
technical job, so it has its own role. An ordinary uploader never gets it — inside a project the
profile may permit the pre-graded kind, and the person still has to hold the role.

An uploader sees every upload in their site, not only their own. "Mine" is a filter on that
list, not the edge of it.

## Pulling from the Remidio API

A manual Remidio API pull is an upload action. The person needs an active upload-profile
assignment for that project, for the Remidio API sync kind, covering every site route the pull
will use. The project list on the screen is only an eligibility list; the server checks the exact
project and routes again before it creates the job.

The person who started a manual job may pause, resume or cancel it only while they still hold the
same sync authority. A System Admin may use break-glass. Another uploader cannot take over the
job merely because they can sync the same project.

The separate administration of Remidio connections, routing profiles and source rules is system
configuration. Only the System Admin may change it.

## Checking what arrived

Nothing can be graded until somebody looks at it and decides it's fit to use.

**Only a verifier does that.** Not the person who uploaded it, not a data manager, not a site
administrator.

Two reasons. The person who uploaded might not be technical, and judging whether data is usable
needs someone who is. And when several kinds of people can all sign the same thing off, nobody
is clearly answerable for it.

Anyone who should be verifying is given the verifier role. That's the whole rule.

Outside a project a verifier covers their own sites. Inside one they cover the sites the project
assigned to them, through a project grant.

## Cleaning up images

Sometimes a patient's name is burnt into the picture itself. Cleaning that up means blanking it
out, or putting it back if the blanking was wrong, and marking whether the image carries details
at all.

Two steps in the work do this: checking, and tidying a dataset. They do the same editing. What
the dataset step doesn't do is decide the data is fit to grade, or create the work that follows
from that decision. It's image correction without the sign-off.

This is also why a dataset curator can see burnt-in names at all. **Seeing them is the only way
to remove them.** It's the last chance to catch a leak before anything leaves.

## Running the AI

The system can read an image with a model and attach that reading to the case.

The run can begin in two different ways, and they get their authority differently.

**A person may ask for it.** That is capture work, so the people who may ask are the ones at or
near capture: the verifier, the clinic optometrist, and field staff. It works the same either side
of the line — outside a project it's your own sites, inside one it's the sites your project grant
or upload assignment covers.

**Or a project may have an automatic rule.** An authorized administrator first chooses the
project, incoming path, disease, model, trigger and eligibility. When routing later brings in a
matching encounter — WAI following a Remidio route, for example — the server acts under that
stored rule. Nobody needs to be signed in at the moment it runs. The authority comes from the
project's rule and the matching event, not from whichever person happened to start the sync.

An automatic rule is not a user role, and the model is not a person. **A model never receives a
login, human roles, project grants, upload assignments or a clinical grading slot.** The worker
sends it only the images selected by the request or rule, and the resulting reading is attributed
to the registered model and version. Storage must not turn the model into an ordinary user merely
because a grade needs an author.

The record of a manual run keeps the person who requested it. The record of an automatic run keeps
the project rule and the event or job that triggered it. Both keep the exact model, integration and
version that produced the answer. Changing an automatic rule affects future runs; it does not
rewrite the authority or attribution of an earlier one.

Re-running a failed one is narrower: administrators, site administrators and data managers only.
A retry spends a call to an outside service, so fewer people can spend it.

Reading the results splits exactly the way counts and lists do. **The summary** — how many ran,
how many worked — is open to everyone who works with those images, analytics included. **The
row-by-row list is not.** Those rows carry patient details, so they belong to the steps that
capture and check: uploaders, verifiers, data managers and field staff. Somebody whose work
begins at grading gets nothing there, and neither does an analytics viewer.

That's written down on its own rather than inherited from the summary. One returns totals and the
other returns records, which is a different disclosure. A rule that handed the row list down from
the summary would have quietly widened it.

## Automatic workers are not users

Scheduled Remidio pulls, OCR, inference, thumbnails and export workers do not log in and do not
receive human roles. They may execute only work already admitted by an authorized service
boundary or by an active stored project rule whose target and routing still match.

For a manual job, the recorded user is attribution, not authority borrowed by the worker. For a
scheduled job, authority comes from the active stored rule and matching event, not from a made-up
user. An interactive retry, resume or change is a new user action and is authorized again before
the worker receives it.

## Out in the field

Field staff use cameras away from the clinic. That is why they are separate roles — a stricter
policy applies to their devices and their sessions. The clinical work is the same.

**Everything on the phone needs a real project relationship.** Hospital access or a site
assignment never opens it, which is stricter than the desktop.

The phone knows which roles you hold and can show them to you, but nothing is decided from what
the phone says. Every upload and every change is checked again on the server.

Through the self-service phone API, your sessions are yours: you can see which devices are signed
in as you and sign any of them out. That self-scoped action never opens another person's session.
The explicit user-administration action below is separate and attributable to its administrator.

Before a field device can sign in, a System Admin or the hospital's user manager issues a
single-use enrolment code for that user. They may approve or block the user's device and revoke
its sessions, but only inside their user-management scope. Blocking a device removes its access;
the device's old token is not authority to continue. These are explicit administrative actions,
not an administrator pretending to be the user.

One gap worth knowing: today a field ophthalmologist can't grade on the phone where a clinic one
can. The two field roles were meant to carry the same distinction as their clinic counterparts —
one grades, one captures — and they don't yet.

## Looking at the work without doing it

Task lists, task details, the image viewer. The people who work with the images browse them —
within their own sites outside a project, within their grant inside one.

Investigators, the access manager and outside collaborators browse their project's tasks too.
Oversight can't oversee what it can't see, and browsing is what feeds regrade and consistency
work.

**Browsing a task is not grading it.** Grading is reached only through a slot, and for project
work through allocation as well. Being able to see the case never turns into being able to read
it.

## Grading

**Outside a project**, two things: the clinical qualification — the `ophthalmologist` role — and
an active slot naming the grading position, site and disease together. `resident`, `resident2`
and `arbitrator` are positions in the workflow, not user roles.

**Inside a project**, the same slot still applies, and the project must also have allocated that
person as one of its graders. Three things, not two, and none of them stands in for another.

A grader sees their own reading, and every other reading on a case they graded — the second
reader's, the arbitrator's, the AI's — so they can see how they compared. Cases they never
touched stay out of reach.

## Who allocates project graders

An allocation is a project saying which already-qualified ophthalmologist may work on which of
its grading targets at which site. It is not a role, and it is not a grading slot. Inside a
project all three still have to agree: `ophthalmologist` says the person is clinically qualified,
the slot says whether they may act as first reader, second reader or arbitrator for that disease
and site, and the allocation says this project selected them for that work.

The project's access manager and its data manager may make or withdraw allocations, but only
inside the part of the project their own grant covers. A site-level manager allocates at that site
and nowhere else. A hospital administrator who has no project grant cannot do it merely because
the site is in their hospital.

Project and Site PIs, the Project Admin and the project's data manager may make or withdraw
allocations inside the part of the project their own grant covers. Each may allocate themselves
or somebody else. The person selected must already be active, hold `ophthalmologist`, and hold
the matching active grading slot. Removing any one of those makes the allocation ineffective
without erasing its history.

Project allocation is always enforced. There is no project-wide switch and no legacy eligibility
fallback for project-owned tasks. A project task is available only when the exact project, site,
grading target, capacity, active clinical role, active grading slot and active allocation all
match. Missing allocation or incomplete facts deny access. A PI, data manager or Project Admin
may arrange allocations inside the part of the project their own grant covers; the allocation
itself becomes authoritative immediately.

The System Admin may use the emergency path for allocation management, but the override creates
no clinical qualification. It never substitutes for `ophthalmologist`, the grading slot, a valid
target or complete coverage.

## When graders disagree

A discrepancy reviewer looks at cases where readings differed and records the settled answer. A
regrade adjudicator settles regrades. They're different roles.

Outside a project they cover their own sites. Inside one they cover the sites the project
allocated to them, through a project grant for that same role.

Exporting the review is a separate release action. An ordinary masked export needs
`data_exporter` over the same tasks. `pii_exporter` is a direct project export role: within its
exact scope it may create either a masked or identifier-bearing export without also holding
`data_exporter`. Mixed or missing scope denies the whole request rather than returning a partial
file. Classical identifier export is System Admin break-glass only.

## Creating work is not doing it

The data manager creates and reassigns regrade tasks and intra-rater batches. Adjudicating a
regrade needs the adjudicator. Grading an intra-rater task needs a slot.

**Neither administrative role can perform the clinical step, and neither clinical role can
create the work.** That holds in both worlds.

## Checking a grader against themselves

The same grader is asked to read some cases twice, at different times, so their consistency can
be measured.

A data manager builds those batches and doesn't grade them. Grading one needs the clinical
qualification and a slot, exactly like ordinary grading. Both data managers and graders see the
resulting figures.

Same shape as everywhere else: whoever creates the work isn't whoever does it.

## Finding things, and making work from them

Search runs across the tasks and images you can already reach. It never widens anything — it
helps you find what is already inside your own patch.

From a search result a data manager can create grading work on the spot, and remove it again.
Only a data manager. Making work is administration, and it's kept away from the people who will
do it.

## Public analytics

The public analytics page is deliberately anonymous and needs no user role or relationship. That
exception covers only the specifically approved system-wide totals, trends and other aggregates
published on that page. It never covers patient rows, identifiers, exports or a drill-down into a
project's clinical results.

Public analytics is a different authorization surface from the authenticated KPI workspaces
below. A route is public only because the policy names it as public; putting it under an
`/analytics` URL does not make it public.

## Signing in and other public entry points

Login and password recovery must be public so a user can establish or recover an identity.
Logout, reauthentication and account changes are self-scoped after that identity exists.
Published help and API documentation may also be public, but only through their own named public
actions. Every other route is authenticated by default; a URL prefix is never authorization.

## KPI analytics: counts and lists are not the same thing

This is the sharpest line in the whole policy, and it's easy to miss because both are called
KPIs.

**A count is a fact about a site's own work.** How many images it captured, how many uploads it
processed, how far its checking queue has moved. That belongs to the site. Site-level access
reaches it and no project involvement is needed — a project's images sitting in your site get
counted without you having any project relationship. Investigators and collaborators read these
for their own project too, as oversight of how it's going.

**A list of records is not.** The table of individual images behind those numbers, and any
export of it, stays locked to the project. Outside a project your hospital or site assignment
reaches it. Inside one you need an explicit project grant.

**Clinical results are not counts in this sense.** Distributions of grades, results and
measurements are the project's findings however they're totalled. A site's claim on its own
throughput doesn't stretch to them.

Where this bites: the list exports are spreadsheets, and spreadsheets are how patient details
walk out of a building — sometimes in a column nobody thinks to check, because a file name can
carry a clinic's patient number without the column ever being called that.

Counts tell you how the work is going. Lists tell you who the patients are. They are not the
same permission, and one should never be granted by way of the other.

## Building a dataset

A dataset creator gathers cases together, tidies them, and finalises the set.

For data belonging to no project, the usual site-level rules apply. For a project's data, only
somebody holding **the whole project** can normally build one. One site isn't enough, however
many sites they hold, because a set drawn from part of a project still goes out under the
project's name. A partial dataset isn't a smaller project dataset — it isn't one.

A project may deliberately allow one of its sites to build its own arm by switching on dataset
creation for that project-site pair. That setting does not grant the work: the person must still
hold the dataset-creator role at that site.

## Sending data out

Building a set and sending it out are different jobs carrying different risks, so they sit with
different people. The exporter exports and hands out share links. The person who built the set
can do neither. Only a finished set goes out.

One person may hold both roles. What matters is that holding only one doesn't quietly give them
the other.

Inside a project, three things are decided per site: whether that site may take grades out,
build datasets, or share them. **Everything starts off.**

Building at a site needs the dataset-creation setting and the dataset-creator role. This setting
covers the complete lifecycle in the dedicated module that generates finalised shareable
datasets: creating, selecting, screening, editing, finalising, reopening and deleting the set.
It does not govern unrelated verification, record editing or analytics.

Sharing or releasing at a site needs the sharing setting and an export role. That setting covers
creating, activating, deactivating and regenerating a share and its export package. Turning it
off immediately disables existing shares created under site authority, but retains them for
audit. Re-enabling the setting does not reactivate them. A setting removes a restriction; it
never grants a role, and project-wide grants are unaffected.

A site always takes out its own encounters and its own pictures, whatever the settings say. That
is its own record of its own work and nothing withholds it. What waits is the **grades** — the
readings the graders made. Those are the project's clinical output, not the site's account of
what it captured. A site takes those out only when the project switches it on for that site
*and* the person holds the exporting role. Neither alone.

The same person holding grants at two sites may export grades at one and not the other.

Letting a patient's name leave the building is the work of `pii_exporter`. It directly authorizes
project export inside its exact grant scope; it is not held on top of `data_exporter`. A
project-wide Project Admin may grant it project-wide or for one site. A site-level Project Admin
cannot grant it. Classical identifier release is available only through System Admin break-glass.

## Downloading a shared dataset

The recipient of a public dataset link does not inherit the exporter's role. The exact active
share, its unexpired token, the one-time password, accepted terms and the exact dataset together
authorize the download. A login session alone does not.

The link reaches no other dataset and stops working when the share is disabled, expired or locked.
The data was authorized for release when the share was created; the public token can never add
patient identifiers that the release action did not authorize. A project release containing
identifiers therefore requires `pii_exporter` before the share is made available. It also
requires recent password confirmation and creates a sensitive-operation audit record without
copying patient identifiers into the audit log.

## Patient names

Three different things get called a patient identifier, and they're handled differently.

**The details on the record** — name, address, and the rest. Reading them is disclosure and
nothing else. They belong to capture, upload and checking, because those steps need to know
which patient this is. Grading, review, analytics, dataset work and export never need to know.

**Names burnt into a picture.** Seeing them is how they get removed, so capture, upload,
checking and dataset tidying all see them. A curator needs to know an image carries a name in
order to crop it out. They never need to know whose name it is.

**The camera's own hidden fields.** These are the strictest, and the reason is worth
understanding: **you don't have to read them to strip them out.** Burnt-in text must be looked
at before it can be cropped, so the correcting steps have to see it. The camera's fields can be
wiped without anybody reading them, so no step in the work needs their contents. They're opened
only to diagnose why a wipe failed. Every path in strips them, so a stored image shouldn't carry
any.

Even the flag saying whether an image still carries them is restricted — not because the flag
reveals a name, but because it says an image is unclean, and that's only useful to somebody who
can clean it.

**Whether a screen shows names is decided by the screen, not by who's looking at it.** Deciding
it from the person's roles unmasks a grader who also happens to upload, on the grading screen
itself. A screen nobody has decided about hides them.

## The camera's report PDFs

These are the camera's own printed reports, with the patient's details on the page. They're
treated as patient data, not as an attachment.

Two kinds of person are specifically kept out: an outside collaborator, and somebody whose only
connection is that they were given a case to grade. **A grading assignment lets you see the
image; it doesn't hand you the report with the name on it.**

The people who open them are scoped uploaders and verifiers, through the designated encounter
browser and verification routes. The source PDF is not masked, is never an export, and is not
shown through later grading routes. The application does not infer a workflow stage for access:
the designated route, uploader/verifier authority and exact encounter scope are the boundary.
Reference-number and UUID viewers apply the same rule.

A shared link opens exactly one document at one hospital. It isn't a key to the folder.

## The technical image details

Size, format, bit depth, brightness, resolution. None of it says anything about a patient, it
sits next to the image in every viewer, and anybody who can see the image can see it. A
collaborator gets this.

It's worth separating in your head from the camera's hidden fields above, because today they
arrive through the same button and they have opposite audiences.

## The other screens

- **Background jobs.** Uploads and processing runs. Most people who work with the data can see a
  job and its result within their own scope, and re-run what it produced. If a job has no Lab
  Unit, that is not a wider scope: only its owner or an administrator can see it unless the
  feature proves a separate project or complete task-derived scope.
- **Screenings.** The records from a screening camp. Most working roles can look. Only a data
  manager can re-run the reading of a screening PDF, or delete one.
- **The reports screen.** Pulls up a DR or glaucoma report by reference, for the working roles.
- **The landing page.** The roles that do day-to-day work.
- **Data-quality reports** — encounters with no capture date, and similar. Administrators only.
  It's a housekeeping list that deliberately looks across everything, so it isn't scoped the way
  ordinary work is.
- **The Glaucoma AI workspace.** A separate place to submit an image and read the model's answer,
  open to the working clinical and data roles.

## Your own account

Your password, your profile, your notifications, your viewer preferences, your phone sessions.
These are yours alone. There is no scope on them because there is nobody else to reach.

The override doesn't open them either. An administrator who needs to act on your account does it
as an administrator, through an action recorded as theirs, rather than stepping into your account
as you.

Reading and updating your own notifications is settled. Sending peer, administrator, broadcast
or system notifications is not yet represented by authorization actions. That is a recorded gap;
those routes must not be consolidated into the new engine until their sender and recipient rules
are decided.

## System administration and user management

System administration belongs only to the `admin` role: system status and maintenance, security,
storage, lookup tables, upload-profile definitions, grading configuration, AI configuration and
Remidio routing. A hospital or project role does not open those controls.

`user_manager` is the one narrow classical exception inside the administration area. Only a
System Admin appoints or removes one. It may create, view, edit, activate and deactivate ordinary
users in its own hospital; assign their ordinary non-project roles, sites and grading slots; and
manage their enrolled mobile devices and sessions. It cannot manage itself, a System Admin,
another user manager or a local administrator; cannot assign `admin`, `user_manager`,
`local_admin`, `pii_exporter` or any project grant; and cannot reach another hospital. The System
Admin appoints local administrators and may do the same work across hospitals through explicit
user-management actions.

`local_admin` remains a hospital-scoped operational role outside projects. It is not a system or
user administrator. `data_manager` administers workflow, not accounts.

## Who hands out access

Only a System Admin appoints Project and Site PIs. A Project PI may appoint a Project Admin inside
its project; a Site PI may appoint a site-scoped Project Admin only inside its own site.

The Project Admin gives out working roles, including project `data_manager`, inside the exact
scope it holds. A project-wide Project Admin may also grant `pii_exporter` project-wide or at one
site; a site-level Project Admin may not grant that sensitive role. Revocation follows the same
ceiling, nobody grants or revokes their own managerial authority, and changes take effect
immediately. Project/Site PIs, Project Admins and project data managers may allocate already-
qualified graders inside their own patch, including themselves and others.

Investigators oversee rather than inherit clinical or operational roles: they do not grade,
verify, settle disagreements or upload merely by being investigators. They may allocate
qualified graders inside their scope. A Project PI covers the whole project. A Site PI covers
its own sites and never the whole project.

Some setup is never handed over: which upload profiles exist, the grading schemes, the automatic
AI runs, the camera routing, and which sites belong to a project.

Outside a project there's the site administrator, who runs a hospital and the sites within it,
and may run more than one.

Before project roles existed, individual people were handed individual capabilities on a project
— this person may export, that one may build datasets. Those older grants still work in places
and are being retired in favour of roles. Nothing new should be given out that way.

## Enforcement details at route boundaries

The route owns transport meaning: it parses and validates supplied project and Lab Unit filters,
loads exact resources and calls the appropriate scope behaviour. The authorization module does
not know route names or query strings. Omitting an optional Lab Unit means every Lab Unit the
chosen action currently authorizes, not every Lab Unit in the system. Supplying a malformed or
unauthorized ID denies; it is never ignored. Classical site reach never opens project rows, and
counts and record lists remain different permissions.

A verifier may reopen or correct verification only before downstream grading exists. Encounter-
set image positions likewise change only while unverified and before downstream grading, through
an exact-scope verifier or System Admin using a locked atomic mutation. The emergency path never
waives these workflow invariants.

Regular and field ophthalmologists grade by the same rule: the role alone is insufficient; the
matching active disease/site/workflow slot is required, plus the matching project allocation for
project work. `resident`, `resident2` and `arbitrator` name those workflow slots, not user roles.
A field optometrist cannot grade.

A data manager creates and reassigns regrade work only inside its classical or project scope.
The selected adjudicator must be active, hold `regrade_adjudicator` and reach that exact task. A
manager may select themselves only when those facts independently hold. An empty eligible scope
denies rather than removing a filter.

Broad backfills, bulk repair, historical recomputation and migration-style maintenance belong to
System Admin alone. Recent password confirmation is required for identifier-bearing exports,
database dump/bulk-export/restore, granting or revoking `admin` or `pii_exporter`, and destructive
bulk maintenance.

Dataset sharing has one authenticated management surface and one public token/OTP download
surface. Duplicate route registrations and legacy authorization aliases are removed; an existing
valid stored token continues through the canonical public route.

## The administrator's override

A system administrator can reach every action except another person's self-scoped actions and
clinical grade submissions, without being assigned to it.

It's an emergency door, not a second normal way in. **It excuses one thing — not being assigned
— and nothing else.** The upload profile still has to fit. The record still gets tagged to the
right project. When it's used to create patient records, that gets written down.

Two doors it never opens: somebody else's own account settings, and signing off a clinical
grade. An administrator acting on someone's account does it as an administrator, which leaves a
trace, rather than as that person. And being an administrator does not make somebody an
ophthalmologist or qualify them to submit a clinical grade.

## The ideas underneath all of it

- Each step's authority stops where the next step begins. Uploading isn't checking. Building a
  dataset isn't releasing it. Creating work isn't deciding it.
- Separating the work doesn't separate the people. One person may hold two roles. The point is
  that holding one doesn't quietly hand them the other.
- Everything is off until somebody turns it on.
- Where somebody can act is a fact about the thing they were given, not a setting on their
  account.
- You can only hand out authority over things you already reach.
- Sensitive things are hidden unless somebody decided otherwise — not shown unless somebody
  decided to hide them.
