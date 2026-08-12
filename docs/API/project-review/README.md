# Project Review API

The Project Review workspace is a read-only, non-PII interpretation of one
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
pre-graded image, package, and task counts; Remidio DR/AMD/glaucoma report and
Wadhwani inference counts; and the currently effective, enabled configuration:

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

## Remembered project navigation

The HTML workspace stores the selected project ID in browser local storage.
Opening the top-level `Projects` link restores that project when it remains in
the server-returned accessible project list; otherwise it opens the first
accessible project. This navigation preference never grants access and is not
used by the API authorization layer.

## Upload inventory

`GET /api/projects/{project_id}/review/uploads?page=1&per_page=100`

`per_page` is capped at 200. The database-paginated inventory includes manual
EncounterSet ZIPs, Remidio API and IITK API EncounterSets, other EncounterSets,
direct images, and pre-graded images. Each row includes only source, UUID,
hospital/lab unit, workflow status, image count, and intake timestamp.

## Gradings

`GET /api/projects/{project_id}/review/gradings`

Aggregates tasks by target type, unified/disease-specific package mode,
disease, and persisted workflow state. State labels map `pending` to Not
graded, `resident_done` to Pending Resident 2, `arbitration` to Pending
adjudication, `resident2_done` to Pending Resident, and `final` to Finalised.

## Errors

- `401`: unauthenticated.
- `404`: project missing or outside the caller's project membership/scope.
