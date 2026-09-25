# Project Review API

The Project Review workspace is a non-PII interpretation of one
project's configuration and operational data. The HTML workspace is available
from the `Projects` navbar link and uses the same service DTOs as these APIs.

## Authorization and scope

- Authentication: active browser session.
- System `admin` may review every project.
- Other users must have an active `ProjectRoleGrant`; legacy active
  `ProjectInvestigator` membership remains a compatibility path.
- Project-wide grants see the full project. Hospital and lab-unit grants see
  only uploads and tasks whose authoritative lab-unit lineage falls inside the
  grant.
- A project grant never expands classical/non-project access.

Every response is non-PII. Upload records use EncounterSet or image UUIDs and
do not return patient name, MRN, patient metadata, report content, grading
comments, or clinical results.

## List projects

`GET /api/projects`

Returns projects in the caller's membership scope.

## Summary

`GET /api/projects/{project_id}/review/summary`

Returns project/scope details; EncounterSet, single-image, total-image,
pre-graded image, EncounterSet grading-workflow, and top-level grading-task counts. It
also returns `% Encounters Verified`, calculated from all in-scope project
`PatientEncounters` (including classic ZIP encounters), where only
`encounter_verified_status = "verified"` counts as verified. Percent values are
rounded to the nearest whole number; an empty denominator returns `0%`. The
metric's `value_suffix` is `%`, and its `help_text` reports the verified and
total encounter counts. The workflow
metric includes hover help explaining its relationship to grading tasks and
listing the underlying configured package names and runtime counts. Remidio
DR/AMD/glaucoma report and Wadhwani inference counts are included only when
their respective integrations are currently active in the project's effective
configuration. The response also includes that enabled configuration:

The summary also returns `grading_completion_percent`, `grading_stage_metrics`
for Need G-1, Need G-2, Need Adjudication, and complete tasks, and `grading_rows`
for top-level encounter tasks only. Explicit `grading_target_level = "encounter"`
tasks are included; legacy rows with a null target level are included only when
their source is `patient_encounter_id`. Image-level targets are omitted from the
summary's task total and progress KPIs. Each row adds `scope_type` (`disease`,
`encounter`, or `legacy`) and `completion_percent`, alongside its stage counts,
`target_group`, `target_type`, `scope_role`, `scope_name`, and
`parent_scope_name`. Root and linked scopes are disease-scoped; unified scopes
are encounter-scoped. Top-level tasks without scope metadata are shown as
legacy/unscoped. Need G-1 counts `pending` and `resident2_done`; Need G-2 counts
`resident_done`; Need Adjudication counts `arbitration`; complete counts `final`.
All task queries use the caller's project/lab scope and contain no patient data.
The `/api/projects/{project_id}/review/gradings` endpoint continues to include
image-level task rows for detailed review.

- upload-profile sources and uploader-selectable modes, diseases, cameras,
  areas, dilation states, EncounterSet types, and authorised assignments;
- currently effective Remidio API bindings (including active date windows) and
  active IITK API destination configuration, without credentials;
- automated and manual analysis rules and their image/task eligibility;
- active single-image and EncounterSet grading targets, task-creation rules,
  current grade definitions, linked disease definitions, and features;
- project annotation tools/classes, configured metadata field definitions,
  referral diseases, and scoped project users/roles/allocations.

Disabled configuration is omitted. Metadata field definitions may identify a
field as PII, but metadata values are never returned.

Each grading target distinguishes `package_applicability` (the stored outer
package gate) from `task_creation` (the runtime-effective interpretation). For
positive-plus-negative-control disease packages, `task_creation` identifies
the referral-positive root disease and control ratio. Grade definitions carry
`target_level` so encounter-level status grades and image-level disease grades
can be rendered separately. Referral diseases identify whether they are a
sampling trigger, linked grading target, ordinary grading target, or
referral-only option.

Grade `guidelines` are returned as sanitized rich text. Only the shared
grading-scheme allow-list of basic formatting tags is retained; attributes and
unsupported tags are removed. HTML clients may render this sanitized field,
while other clients may convert it to plain text.

Unified EncounterSet package definitions are ordered as EncounterSet-level
grading schemes, configured per-image grading schemes, and then any active
linked disease schemes referenced by those per-image schemes. A configured
per-image scheme is not labeled as linked merely because unified packages have
no root disease scope.

## Remembered project navigation

The HTML workspace stores the selected project ID in browser local storage.
Opening the top-level `Projects` link restores that project when it remains in
the server-returned accessible project list; otherwise it opens the first
accessible project. This navigation preference never grants access and is not
used by the API authorization layer.

## Direct image browser

`GET /api/projects/{project_id}/review/uploads?page=1&per_page=100&status=pending&lab_unit_id=6&date_from=2026-09-01&date_to=2026-09-15`

`per_page` is capped at 200. This database-paginated browser contains direct
and pre-graded single-image uploads only; EncounterSets remain in the separate
EncounterSet browser. Filters accept verification `status`, an accessible
`lab_unit_id`, and inclusive ISO upload-date bounds. Each row includes UUID,
filename, disease, uploader, hospital/lab unit, verification status, and upload
timestamp. The date is never interpreted as a patient capture date.

The HTML page at `/projects/{project_id}/uploads` renders the first page. Its
filter and pagination controls issue HTMX GETs to this API. With
`HX-Request: true`, the API returns the shared image-grid partial and an
`HX-Push-Url` header preserving the browser URL; otherwise it returns JSON.
The grid provides an immediate full-image quick view and shows uploader name;
an upload remark is exposed on hover. Users with an active project `verifier`
or `project_admin` grant in the image's exact project/lab scope can HTMX-load a
verification panel on the right of the browser. It keeps PII status, uploader
remark, rapid Verify/Not Gradable actions, and the same ungradable reason
choices as EncounterSet verification together. A decision advances the panel
to the next pending accessible image and refreshes the grid. Project Admins
also receive an audited editor link that opens in a new tab. Verification
remains blocked while the active PII detector result is `detected`.

### Direct-image verification panel

`GET /api/projects/{project_id}/direct-images/{uuid}/verification` returns the
HTMX panel for an exact, authorized image. `POST` to the same endpoint accepts
form fields `status` (`verified` or `not_gradable`) and `remarks`. A non-empty
reason is required for `not_gradable`. Both operations require an active
`verifier` or `project_admin` grant containing the image's project and lab
unit; out-of-scope images return `404`. POST requires the normal CSRF form
token. A successful response contains the next pending accessible image panel,
or the queue-complete partial, and emits `HX-Trigger: direct-image-verified`.

## Gradings

`GET /api/projects/{project_id}/review/gradings`

Aggregates tasks by target type, unified/disease-specific package mode, and
disease scope. Each row reports `task_count`, `first_grading_count`,
`second_grading_count`, `adjudication_count`, and `final_count`. First grading
includes `pending` plus the edge case where Resident 2 graded first;
second grading maps `resident_done`, adjudication maps `arbitration`, and
complete maps `final`. Rows also include `scope_type` and `completion_percent`.
This detailed endpoint continues to include image-level tasks. EncounterSet
rows without persisted scope lineage are reported as legacy/unscoped rather
than visually inheriting the preceding scope.

## Errors

- `401`: unauthenticated.
- `404`: project missing or outside the caller's project membership/scope.
