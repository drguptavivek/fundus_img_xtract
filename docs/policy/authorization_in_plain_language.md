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

## Out in the field

Field staff use cameras away from the clinic. That is why they are separate roles — a stricter
policy applies to their devices and their sessions. The clinical work is the same.

**Everything on the phone needs a real project relationship.** Hospital access or a site
assignment never opens it, which is stricter than the desktop.

The phone knows which roles you hold and can show them to you, but nothing is decided from what
the phone says. Every upload and every change is checked again on the server.

Your sessions are yours. You can see which devices are signed in as you and sign any of them out.
Nobody else can, an administrator included.

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

## When graders disagree

A discrepancy reviewer looks at cases where readings differed and records the settled answer. A
regrade adjudicator settles regrades. They're different roles.

Outside a project they cover their own sites. Inside one they cover the sites the project
allocated to them, through a project grant for that same role.

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

## Counts and lists are not the same thing

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

Building at a site needs the dataset-creation setting and the dataset-creator role. Sharing or
releasing at a site needs the sharing setting and the data-exporter role. A setting removes a
restriction; it never grants a role.

A site always takes out its own encounters and its own pictures, whatever the settings say. That
is its own record of its own work and nothing withholds it. What waits is the **grades** — the
readings the graders made. Those are the project's clinical output, not the site's account of
what it captured. A site takes those out only when the project switches it on for that site
*and* the person holds the exporting role. Neither alone.

The same person holding grants at two sites may export grades at one and not the other.

Letting a patient's name leave the building is its own separate permission, held on top of
whatever allowed the data out.

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

The people who do open them are the ones in the steps before grading — the verifier and the
optometrist, and field staff, since they're the ones capturing.

A shared link opens exactly one document at one hospital. It isn't a key to the folder.

## The technical image details

Size, format, bit depth, brightness, resolution. None of it says anything about a patient, it
sits next to the image in every viewer, and anybody who can see the image can see it. A
collaborator gets this.

It's worth separating in your head from the camera's hidden fields above, because today they
arrive through the same button and they have opposite audiences.

## The other screens

- **Background jobs.** Uploads and processing runs. Most people who work with the data can see a
  job and its result within their own scope, and re-run what it produced.
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

## Who hands out access

Only a system administrator appoints the people who govern a project. Nobody else can hand that
out, at any level.

The project's access manager gives out the working roles, and only within their own patch —
somebody covering one site can't grant anything beyond that site. That single rule is what lets
a small project keep one access manager and a large one appoint one per site, without the policy
being any different.

Investigators watch. They don't grade, verify, settle disagreements or upload anything. A
project investigator covers the whole project. A site investigator covers their own sites and
never the whole project.

Some setup is never handed over: which upload profiles exist, the grading schemes, the automatic
AI runs, the camera routing, and which sites belong to a project.

Outside a project there's the site administrator, who runs a hospital and the sites within it,
and may run more than one.

Before project roles existed, individual people were handed individual capabilities on a project
— this person may export, that one may build datasets. Those older grants still work in places
and are being retired in favour of roles. Nothing new should be given out that way.

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
