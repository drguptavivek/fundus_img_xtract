# Project-Level Annotation Policy and GPU Grading Workbench

Status: Approved implementation plan

## 1. Purpose

Define which annotation tools and annotation classes are available within a
project, and deliver a new grading workbench that applies that policy through a
React, TypeScript, PixiJS, and WebGL2 interface. The grading context continues
to determine which grades and grading features apply.

The policy is project-level rather than disease-level. A project may use more
than one disease, and each disease may have its own grading scheme, grades, and
features. EncounterSet grading may also be disease-specific or unified. The
annotation policy must work with all of these arrangements without duplicating
or replacing the existing grading configuration.

The first public release covers:

- enabling or disabling annotations for a project;
- choosing the annotation tools available in that project;
- applying a default localization policy to grading-feature-backed classes;
- configuring project-defined annotation classes;
- allowing or disallowing multiple instances for each project-defined class;
- resolving the effective annotation palette for a grading task or linked
  grading panel;
- validating submitted annotations against the resolved project policy;
- normalizing saved annotation instances and full-resolution segmentation
  masks instead of treating `Grade.feature_geometry_json` as authoritative;
- supporting every current grading workflow through one reusable domain and
  API boundary; and
- allowing each grader to choose the new workbench or the legacy interface
  during rollout.

The workbench must support resident, resident2, arbitrator, revision, linked
multi-disease, regrade adjudication, intra-rater, unified EncounterSet, and
disease-specific EncounterSet grading. It must preserve image- and
encounter-level targets, read-only states, atomic multi-panel submission,
Save & Close, and Save & Next behavior.

## 2. Non-Goals

The first release does not define:

- COCO, YOLO, IITK, DICOM, or other export contracts;
- automatic submission to an external annotation API;
- disease-to-task or grading-scheme selection;
- grader eligibility;
- a replacement for grading-scheme configuration;
- a new consensus or arbitration workflow; or
- standardized image tags. Project-configured tags are a compatible future
  extension but are not required for the first implementation.

OpenCV.js, OpenSeadragon, Cornerstone3D, raw WebGL, and experimental WebGPU are
not runtime foundations for this release. OpenCV.js may be considered later
for advanced preprocessing that cannot be expressed as a versioned shader.

Existing grade comments remain free text and are not converted into annotation
classes or standardized tags.

## 3. Design Decision

The project annotation policy and the grading configuration have separate
responsibilities:

```text
Project Annotation Policy
  tools + feature defaults + feature overrides + project classes
                              +
Active Grading Context
  task/panel -> grading scheme -> selected grade -> selected features
                              =
Resolved Annotation Tools and Classes
```

The grading configuration remains authoritative for:

- which disease or unified grading target a task represents;
- which grading scheme applies;
- which grades are available;
- which features belong to each grade;
- whether EncounterSet grading is unified or disease-specific; and
- task creation.

Project grader allocation is a separate concern. Upload & Grading Profiles
define which tasks exist, while the project allocation module determines which
resident pool or arbitrator pool may receive each resolved task target. Legacy
projectless tasks retain disease-and-lab eligibility.

The annotation policy answers only:

- whether annotation is enabled for the project;
- which drawing tools are available;
- how grading features may be localized;
- whether a particular grading feature overrides the project default; and
- which additional project-defined classes are available.

There is no disease identifier on the project annotation policy. Disease and
grading-scheme scope are obtained from the active grading task or linked panel.

## 4. Annotation Class Sources

The resolved class palette has two explicit sources.

### 4.1 Grading-feature-backed classes

After a grader selects a grade, the features configured for that grade become
eligible annotation class names. A feature becomes an active annotation class
when the grader selects that feature.

Rules:

- the stable identity is `grading_feature_id`;
- the displayed class name is the configured feature label;
- the label is snapshotted with the saved annotation for history;
- every grading-feature-backed class always allows multiple annotation
  instances;
- multiplicity is not configurable for grading features;
- the project feature default controls allowed localization and preferred
  tool; and
- a project may override tools or localization for a specific grading feature.

Selecting a feature is an image- or grading-target-level assertion that the
finding is present. Drawing geometry localizes one or more instances of that
finding. A selected feature may exist without geometry when localization is
optional.

### 4.2 Project-defined classes

A project may define classes that are not grading features, such as
`eye_region`, `iris`, `pupil`, or `lesion`.

Rules:

- each class has a stable snake-case key and a display label;
- the class is owned by the project annotation policy;
- the class declares its allowed localization and tools;
- `multiple_instances` is configurable for each class;
- project-defined classes are not inferred from a disease or grading-scheme
  name; and
- project-defined classes remain separate from selected grading features even
  when their labels look similar.

## 5. Tool and Geometry Vocabulary

The first release uses stable tool keys:

| Tool key | Purpose | Authoritative geometry |
|---|---|---|
| `box` | Draw and resize an axis-aligned bounding box | Pixel-space box |
| `polygon` | Draw or edit a closed outline | Pixel-space polygon |
| `brush_mask` | Paint or erase a segmented region | Pixel-space/grid mask |
| `ellipse` | Draw and resize an ellipse | Ellipse plus enclosing ROI |
| `pyramid` | Draw the existing cone-like shape | Polygon plus enclosing ROI |

The policy describes allowed user-facing tools. The storage service continues
to validate the resulting geometry independently.

### 5.1 Localization policy

Each resolved class uses one of these policies:

| Policy | Meaning |
|---|---|
| `none` | Image-level assertion only; geometry is not allowed |
| `box` | A bounding box is the accepted localization |
| `segmentation` | Polygon or mask segmentation is required |
| `box_or_segmentation` | A box is sufficient and segmentation is an optional refinement |

The default for grading-feature-backed classes is expected to be
`box_or_segmentation`, with `box` as the preferred tool. This keeps the common
workflow quick while allowing greater precision where useful.

### 5.2 Box-to-segmentation refinement

A class configured as `box_or_segmentation` follows this lifecycle:

```text
Box only
  -> box is authoritative

Segmentation added or refined
  -> segmentation is authoritative
  -> bounding box is derived from the segmentation
```

The box and segmentation must not remain independently editable. Once a
polygon or mask replaces/refines a box, the server derives the current box from
the segmentation whenever needed.

For polygons, the derived box is:

```text
x = min(point.x)
y = min(point.y)
w = max(point.x) - min(point.x)
h = max(point.y) - min(point.y)
```

For masks, the derived box encloses all occupied cells or pixels after they are
projected into the original image's pixel coordinate space.

Empty segmentation does not have a valid bounding box and is incomplete.

## 6. Multiple-Instance Rules

Multiplicity depends on the source of the class.

| Class source | Multiple instances |
|---|---|
| Grading feature | Always allowed; fixed system rule |
| Project-defined class | Configured with `multiple_instances=true|false` |

When a project-defined class has `multiple_instances=false`:

- the first drawing creates the single annotation instance;
- selecting the class again selects the existing instance;
- the add-another action is disabled;
- changing from a box to segmentation refines the same instance; and
- the server rejects an attempt to create a second active instance.

When `multiple_instances=true`, each drawing creates a separate annotation
with its own stable instance identifier.

A single brush mask may contain disconnected painted regions while still
being one annotation instance. Multiple instances mean independently
selectable and editable annotation objects, not merely disconnected pixels.

## 7. Configuration Contract

An illustrative resolved configuration is:

```json
{
  "project_id": 7,
  "enabled": true,
  "revision": 1,
  "enabled_tools": ["box", "polygon", "brush_mask"],
  "default_feature_policy": {
    "localization": "box_or_segmentation",
    "preferred_tool": "box",
    "allowed_tools": ["box", "polygon", "brush_mask"]
  },
  "feature_overrides": [
    {
      "grading_feature_id": 101,
      "localization": "segmentation",
      "preferred_tool": "polygon",
      "allowed_tools": ["polygon", "brush_mask"]
    }
  ],
  "project_classes": [
    {
      "id": 21,
      "key": "iris",
      "label": "Iris",
      "localization": "segmentation",
      "preferred_tool": "polygon",
      "allowed_tools": ["polygon"],
      "multiple_instances": false,
      "active": true
    },
    {
      "id": 22,
      "key": "lesion",
      "label": "Lesion",
      "localization": "box_or_segmentation",
      "preferred_tool": "box",
      "allowed_tools": ["box", "polygon", "brush_mask"],
      "multiple_instances": true,
      "active": true
    }
  ]
}
```

`multiple_instances` is deliberately absent from `default_feature_policy` and
`feature_overrides` because grading features always permit multiple instances.

## 8. Runtime Resolution

The server resolves the effective annotation context from the task rather than
accepting project, disease, or grading-scheme identifiers from the browser.

### 8.1 Image-level disease grading

The selected disease grade supplies its feature vocabulary. Geometry attaches
to the image being graded.

### 8.2 Disease-specific EncounterSet grading

The active disease task/panel supplies its grading scheme, grade, and features.
The project annotation policy is shared, but every feature-backed annotation
retains its task and feature identity. Geometry attaches to a specific image in
the set.

### 8.3 Unified EncounterSet grading

The unified grading scheme supplies the grade and feature vocabulary. The
classification may apply to the encounter, but drawable geometry still
requires a specific image UUID within the encounter.

An encounter-level finding without an image is an image-free assertion, not an
annotation geometry.

### 8.4 Linked multi-disease grading

Each linked grading panel resolves features from its own task and grading
scheme. Feature classes from different panels must not be merged into an
ambiguous shared list.

Project tools and project-defined classes may be shared, while feature-backed
annotations retain their originating task/panel context.

## 9. Persistence

### 9.1 `project_annotation_policies`

- `id`
- `project_id`, unique and non-null
- `enabled`
- `default_localization`
- `preferred_tool_key`
- `revision`
- `created_at`, `updated_at`
- creator/updater audit fields where supported

### 9.2 `project_annotation_tools`

- `id`
- `policy_id`
- `tool_key`
- `enabled`
- optional `settings_json`
- unique `(policy_id, tool_key)`

### 9.3 `project_annotation_feature_overrides`

- `id`
- `policy_id`
- `grading_feature_id`
- `localization`
- `preferred_tool_key`
- `active`
- unique `(policy_id, grading_feature_id)`

There is no multiplicity column on feature overrides.

### 9.4 `project_annotation_feature_override_tools`

- `feature_override_id`
- `tool_key`
- unique `(feature_override_id, tool_key)`

### 9.5 `project_annotation_classes`

- `id`
- `policy_id`
- `key`
- `label`
- `localization`
- `preferred_tool_key`
- `multiple_instances`
- `active`
- timestamps and audit fields
- unique active key within a policy

### 9.6 `project_annotation_class_tools`

- `project_annotation_class_id`
- `tool_key`
- unique `(project_annotation_class_id, tool_key)`

Published/saved annotations must retain the policy revision and class label
snapshot that applied when they were created. Deactivating a class or tool must
not delete or reinterpret historical annotations.

### 9.7 `annotation_sets`

An annotation set is the normalized annotation owner for one submitted grade.

- UUID primary key;
- exactly one of `grade_id` or `intra_rater_grade_id` is non-null;
- one set per owning grade;
- schema version and applied policy revision;
- timestamps; and
- a database check enforcing exactly one owner.

The grade is flushed before its annotation set is created, but both writes are
committed in the same grading transaction.

### 9.8 `annotation_instances`

Each independently selectable object is one row containing:

- stable UUID and annotation-set foreign key;
- concrete image UUID;
- class source: `grading_feature`, `project_class`, or reserved structured
  measurement;
- nullable grading-feature or project-class foreign key;
- class key and label snapshots;
- applied policy revision;
- geometry type and type-specific JSON;
- server-derived `bbox_x`, `bbox_y`, `bbox_w`, and `bbox_h`;
- instance ordering and lock state; and
- timestamps.

Feature and project-class foreign keys must not make historical annotations
unreadable after configuration deactivation. The snapshots remain the
historical meaning of the annotation.

### 9.9 `annotation_mask_tiles`

Brush segmentation is stored in original-image pixel space as sparse
`256 x 256` binary tiles. Only non-empty tiles are persisted.

- annotation-instance foreign key;
- tile `x` and `y` indexes;
- actual edge-tile width and height;
- lossless binary PNG bytes;
- content checksum; and
- unique `(annotation_instance_id, tile_x, tile_y)`.

The server decodes and validates every submitted tile, rejects pixels outside
the image, and derives the instance bounding box from occupied pixels. The
browser must not submit a separately editable authoritative box for a mask.

## 10. Service and DTO Boundary

Annotation policy resolution, normalized annotation persistence, and workbench
workflow commands belong in cohesive deep service modules. Page and API routes
should only authenticate, authorize, parse transport input, call the service,
and serialize typed DTOs.

The service is responsible for:

- loading the project from the grading task;
- enforcing lab/project scope;
- resolving the correct task or linked-panel grading context;
- deriving feature-backed classes from the selected grade;
- applying project defaults and feature overrides;
- adding active project-defined classes;
- intersecting per-class tools with project-enabled tools;
- validating multiplicity and geometry; and
- returning stable DTOs for the grading UI and future consumers.

Existing eligibility, revision, task-state, consensus, next-task, linked-panel,
and EncounterSet rules must be extracted from the current page routes into
reusable grading services. The legacy pages and the React APIs call those same
services; the workbench must not reimplement grading business rules in
TypeScript or API routes.

The browser must not be allowed to select a different project, disease, scheme,
or feature context by submitting identifiers that were not resolved from the
task.

## 11. API Surface

All new endpoints live under the `api` package and require normal CSRF
protection for unsafe methods.

### 11.1 Administration

```text
GET /api/projects/<project_id>/annotation-policy
PUT /api/projects/<project_id>/annotation-policy
```

The administration API documents:

- permitted roles;
- project and lab-unit scoping;
- request and response DTOs;
- validation errors;
- CSRF requirements; and
- activation/deactivation behavior.

### 11.2 Grading workspace resolution

```text
GET /api/grading-tasks/<task_uuid>/annotation-context
```

For linked grading, the response contains a separately resolved context for
each task/panel. It returns only classes and tools permitted for the requesting
user and task.

The selected grade may be supplied as a validated query parameter or resolved
incrementally after grade selection. The service must verify that the grade
belongs to the task's configured grading scheme.

### 11.3 Workbench workspace and submission

```text
GET  /api/grading-workbench/workspaces/<target_type>/<target_ref>?slot=<slot>
POST /api/grading-workbench/submissions
GET  /api/annotation-instances/<annotation_uuid>/mask-tiles
GET  /api/annotation-instances/<annotation_uuid>/mask-tiles/<tile_x>/<tile_y>
```

`target_type` is a documented enum covering dual/linked tasks, regrade tasks,
intra-rater tasks, legacy EncounterSet tasks, and EncounterSet packages. The
workspace response uses a common DTO containing:

- an opaque context revision;
- workflow and navigation capabilities;
- separately scoped task panels;
- eligible grades and features;
- resolved annotation tools and classes;
- secured image descriptors;
- existing normalized annotations;
- read-only reasons; and
- viewer preferences.

Submission is multipart data with a typed JSON manifest and referenced PNG
mask-tile parts. Each panel contains its grade, selected features, comment,
image-specific annotations, measurements, action, and context revision. The
service returns structured next and dashboard URLs after success.

The API returns `409` when the task, policy, or revision changed after the
workspace loaded; `422` for annotation or grading validation; `403` for scope
or eligibility failures; and `400` for malformed transport data. Linked and
package submissions are atomic.

### 11.4 Viewer preference

Extend the existing viewer-settings API with
`grading_interface: "legacy" | "workbench"`. Existing users default to
`legacy` until they choose the new interface. Unsafe preference changes require
CSRF.

## 12. Administration UI

Add an `Annotations` section within project administration, near the project's
Upload & Grading configuration.

The workspace contains:

1. An enable/disable control for project annotations.
2. Project-wide tool toggles.
3. Default grading-feature policy:
   - localization;
   - preferred tool; and
   - allowed tools.
4. Feature-specific overrides grouped by grading scheme and grade.
5. Project-defined class management:
   - stable key;
   - display label;
   - localization;
   - preferred and allowed tools;
   - multiple instances; and
   - active state.

Mutations that affect tool selectors, class selectors, modal forms, or counts
must refresh the shared annotation-policy workspace so hidden form options do
not become stale.

## 13. React Grading Workbench

The workbench is a full-page React and TypeScript application built with Vite.
React owns task state, grade/feature controls, comments, navigation, annotation
class selection, and accessibility. PixiJS owns the viewport directly; pointer
movement and brush rendering must not trigger React reconciliation.

The interface uses:

- a persistent central image viewport;
- a compact grade and feature panel;
- a policy-resolved annotation toolbar and instance list;
- an image strip for EncounterSets;
- isolated linked-disease panel switching;
- a progress and navigation header;
- mouse, keyboard, pen, and tablet touch controls; and
- explicit read-only and stale-context states.

Phones are not editing targets for the first release. They receive a clear
unsupported or view-only state rather than a compressed, unsafe grading form.

### 13.1 Annotation behavior

When the grading screen loads:

1. Resolve the task's project annotation policy.
2. Hide annotation controls if the policy is absent or disabled.
3. Show only project-enabled tools.
4. After grade selection, resolve feature classes belonging to that grade.
5. Activate a feature-backed class only after the feature is selected.
6. Add active project-defined classes to the class selector.
7. When a class is selected, enable only its permitted tools.
8. Prefer the configured tool, normally `box`.
9. Apply the fixed or configured multiplicity rule.
10. Preserve existing locked annotation behavior and task/panel isolation.

For a single-instance project class, selecting the class after an annotation
exists selects that annotation instead of creating another.

### 13.2 GPU viewport

PixiJS v8 uses its production WebGL renderer. The workbench requires WebGL2,
detects unsupported devices before loading a task, and offers the legacy view.
Experimental WebGPU is not enabled.

One camera transform controls the source image, vector geometry, segmentation,
loupe, and CDR/RDR measurement. Source images are divided into textures no
larger than the device's reported maximum texture size. Filters are versioned
shaders applied only to the retinal image layer so class colors are unchanged.

Vector objects use Pixi scene objects and explicit edit handles. Full-resolution
mask tiles are mutable GPU textures; brush operations update only dirty tiles.
PNG encoding/decoding and mask-derived calculations run in a Web Worker. The
renderer draws on demand when idle and continuously only during active
interaction.

### 13.3 Local recovery

Unsubmitted work is recovered locally through IndexedDB, keyed by user,
workflow target, slot, and server context revision. Recovery includes grading
selections, comments, vector geometry, and dirty mask tiles.

On reload, the user explicitly restores or discards the draft. A draft from a
stale context is not silently applied. Successful submission clears it.
Drafts do not synchronize between devices and are not server-side records.

### 13.4 CVAT canvas assessment

The CVAT `develop` branch was reviewed on 2026-08-01 as a possible replacement
for the custom viewport. The reviewed module is
[`cvat-canvas`](https://github.com/cvat-ai/cvat/tree/develop/cvat-canvas), not a
deployment of the complete CVAT application.

#### Capabilities that are relevant to this workbench

`cvat-canvas` is a mature imperative TypeScript annotation engine. Its public
API and internal handlers provide:

- rectangle, polygon, polyline, point, ellipse, cuboid, skeleton, and mask
  objects;
- drawing, selection, activation, highlighting, focus, editing, and deletion
  event lifecycles;
- grouping, joining, merging, splitting, polygon slicing, and region
  selection;
- pan, zoom, rotation, fit-to-window, grid, snap, z-order, object opacity, and
  label/group/instance color modes;
- brush and eraser mask editing, plus polygon-add and polygon-subtract mask
  operations;
- positive/negative point and box interaction hooks suitable for assisted
  annotation tools;
- issue regions, locked/hidden objects, conflict highlighting, and read-only
  editing controls; and
- a CSS image-filter hook that can express browser brightness, contrast,
  saturation, and similar presentation filters.

Its explicit interaction modes and emitted events are particularly useful
references for cancel behavior, tool switching, selection, edit completion,
and prevention of conflicting simultaneous operations. These behaviors should
inform the workbench state machine and frontend tests even though the renderer
is not adopted.

#### Rendering and mask architecture

`cvat-canvas` is not a WebGL renderer. It uses SVG.js and SVG DOM elements for
vector annotations. Its mask layer uses Fabric.js over a Canvas2D element.
Image adjustment is a CSS filter on the background image rather than a shader
pipeline.

Mask instances are cropped to their occupied bounding rectangle and serialized
as run-length encoded pixels followed by `left`, `top`, `right`, and `bottom`.
This provides a deterministic box for a mask and is efficient for many compact
objects. It also demonstrates the desired rule that a segmentation can produce
its bounding box without a second independently editable box.

The workbench must not adopt that representation unchanged. A large edited
mask is decoded into a contiguous `ImageData`/canvas region during editing.
There is no sparse full-resolution tile cache, dirty-tile upload contract, GPU
texture painting, or worker-owned tile pipeline. The proposed 256 by 256 mask
tiles therefore remain the authoritative workbench design. Run-length encoding
may be evaluated as a per-tile compression option, but only if benchmarks show
a benefit over PNG and the API continues to treat the tile as an opaque,
checksummed payload.

#### Integration and ownership concerns

The module is not a React component or a neutral geometry library. React could
host it through a lifecycle wrapper, but the application would need to adapt
our DTOs to CVAT-shaped `frameData` and object-state objects. Those objects
include CVAT concepts such as client IDs, label and group objects, frame
numbers, sources, attributes, z-order, lock state, and skeleton elements.

Direct adoption would therefore require an adapter or maintained fork while
leaving the following responsibilities in this application:

- project annotation policy resolution;
- grade and selected-feature resolution;
- feature-backed and project-defined class identity;
- allowed-tool and localization enforcement;
- project-class multiplicity validation;
- image/encounter target ownership and linked-panel isolation;
- normalized annotation persistence and mask-tile APIs;
- grading workflow, comments, submission, consensus, and navigation; and
- RBAC/ABAC, lab/project scope, CSRF, revision, and audit enforcement.

CVAT tags are also not a substitute for the deferred project-configured image
tags in this plan. Image-level label vocabulary and assignments are domain data
outside the canvas renderer.

#### Selective reuse and reduced-fork option

Adoption is not all-or-nothing. The MIT license permits the project to copy,
modify, and redistribute selected `cvat-canvas` components while retaining the
required notices. A reduced fork is therefore a valid implementation candidate
if it saves more interaction work than it adds in long-term maintenance.

The intended selection boundary is:

| Treatment | CVAT capability or component | Project treatment |
|---|---|---|
| Keep or adapt | Interaction modes, cancellation, activation, selection, edit handles, polygon editing, coordinate transforms, keyboard/event conventions | Convert to typed, renderer-neutral workbench services and tests where practical |
| Keep if justified | Rectangle, ellipse, polygon, point, grouping, slicing, joining, merging, mask-to-box calculation, RLE utilities | Retain only capabilities enabled by the project tool vocabulary or required by near-term assisted annotation |
| Remove | Video interpolation/tracking, cuboids, skeletons, frame-specific tracking state, CVAT issue UI, CVAT label/group/attribute models, and unused complex operations | Exclude from the production bundle and public workbench contract |
| Replace | CVAT `frameData`, object states, persistence, tags, class vocabulary, permissions, workflow, and submission | Use this application's typed annotation-context, policy, normalized storage, grading services, and APIs |
| Replace for production masks | Fabric.js/Canvas2D mask editing and whole cropped-mask lifecycle | Use PixiJS dirty GPU tiles, worker encoding, and the normalized mask-tile API |
| Add | Pyramid/cone geometry, retinal filters, loupe, CDR/RDR measurement, IndexedDB recovery, project class multiplicity, linked grading panels, and grading controls | Implement as first-class workbench modules governed by the project contract |

There are two technically viable levels of reuse:

1. **Source-level extraction.** Port small, cohesive algorithms and interaction
   semantics into our own typed modules. This gives the cleanest domain and
   renderer boundary and is preferred for coordinate helpers, polygon editing,
   cancellation rules, and mask-to-box/RLE utilities.
2. **Reduced interaction-layer fork.** Start from a pinned `cvat-canvas`
   revision, delete unsupported shape/workflow paths, wrap the remaining engine
   behind our DTOs, and progressively replace its image and mask layers. This
   can accelerate mature vector editing, but it creates a maintained fork and
   requires careful separation between the SVG coordinate system and the PixiJS
   camera.

The reduced fork must expose only our workbench interface. Flask APIs and the
database must never receive CVAT object states, client IDs, label objects, or
mask payloads. Translation occurs at the frontend adapter boundary, and saved
coordinates remain original-image pixel coordinates under the normalized
annotation contract.

Removal must be structural rather than merely hiding toolbar buttons. Unused
handlers, state transitions, dependencies, CSS, events, and serialization paths
must be excluded so they cannot enlarge the bundle or become accidental public
behavior. Conversely, useful CVAT capabilities should not be copied merely
because they exist; each retained component needs a current project use case,
unit tests, license attribution, and an identified maintainer.

#### Product and maintenance concerns

- SVG DOM rendering is proven for interactive vectors but does not provide the
  GPU image, mask, loupe, and measurement composition required by this plan.
  Performance with 4K/8K retinal images, large masks, and hundreds of visible
  objects would require a local benchmark rather than an assumption based on
  the full CVAT product.
- CSS image filters do not provide our versioned retinal-image shader contract
  and make it harder to guarantee identical rendering and measurement-layer
  isolation across browsers.
- The mask editor is Canvas2D/Fabric-based and does not meet the dirty GPU-tile
  or worker-offloaded encoding requirements.
- The upstream package uses older SVG.js plugin APIs and obtains some
  dependencies from the CVAT monorepo. A standalone build must prove that its
  dependency graph, CSS, and assets can be isolated and upgraded safely.
- CVAT primarily supports Chromium. Its published browser notes do not claim
  Safari/WebKit support, which conflicts with a tablet-capable workbench if
  reference devices include iPads.
- The engine includes video tracking, cuboids, skeletons, complex object
  operations, and other state that this release does not require. These paths
  can be removed in a fork, but safely untangling shared handlers and state is
  implementation work and must be measured rather than assumed trivial.
- It does not provide the existing pyramid/cone annotation, retinal loupe,
  CDR/RDR measurement, local IndexedDB recovery, or our grading-card behavior.
- Following the upstream `develop` branch directly would expose grading to
  upstream API and behavior changes. A pinned version or fork would still need
  security, compatibility, and accessibility ownership within this project.

The CVAT repository and `cvat-canvas` sources use the MIT license. Any copied
or adapted implementation must preserve the required copyright and license
notice and must be recorded in the application's third-party notices.

#### Decision

The complete `cvat-canvas` package and CVAT domain model are not selected for
wholesale adoption. Selective source reuse and a reduced interaction-layer fork
remain explicit candidates. The React application, our typed workbench DTOs,
project policy, normalized persistence, and grading services remain fixed
architectural boundaries.

PixiJS/WebGL2 remains the production image, filter, loupe, measurement, and
full-resolution mask renderer. The bounded prototype in Phase 4 will decide
whether vector interaction should be implemented directly in PixiJS or
accelerated with a pruned CVAT-derived SVG interaction layer above the same
camera. A hybrid is acceptable only if it maintains one authoritative camera
transform and passes coordinate, latency, cleanup, and accessibility tests.

The prototype must compare the reduced CVAT-derived path with the direct PixiJS
path on the same 4K and 8K fixtures. It must test brush latency, memory
stability, vector-object load, zoom/pan frame time, mask round trips, pen/touch
behavior, Safari on any required iPad, dependency isolation, React lifecycle
cleanup, and the effort required to remove upstream-only code. The performance
and workflow acceptance gates in this document still apply; passing a basic box
or polygon demonstration is not sufficient to select the interaction layer.

## 14. Server Validation

On save, the server verifies:

- the task resolves to the project associated with the policy;
- annotations are enabled for that project;
- every tool is enabled by the project;
- every feature-backed class belongs to the selected grade;
- every feature-backed class corresponds to a selected feature;
- every project-defined class is active and belongs to the project policy;
- the submitted geometry type is allowed for the class;
- single-instance project classes have at most one active annotation;
- geometry coordinates are finite and within the original image bounds;
- polygon and mask geometry is non-empty when segmentation is required; and
- encounter-level geometry identifies a concrete image UUID.

The service must not trust client-provided class labels, project IDs, disease
IDs, or policy revisions without resolving them from stored records.

## 15. Configuration Lifecycle and History

- Existing annotations remain visible if a class or tool is later disabled.
- Deactivation prevents new annotations; it does not delete historical rows.
- A project policy with linked annotations is deactivated rather than deleted.
- Project-defined class keys are stable and cannot be silently reused with a
  different meaning.
- Saved annotations snapshot the display label and policy revision.
- A draft loaded under one policy revision must not be silently validated under
  a newer revision without warning or refresh.

## 16. Compatibility with Current Geometry

The existing `feature_geometry_json` contract already supports multiple items
for the same grading feature and stores original-image pixel coordinates.

Migration and compatibility rules:

- existing feature-linked items are grading-feature-backed annotations;
- their multiplicity remains valid because grading features always allow many;
- `box` remains an authoritative box until refined;
- `polygon` and `region` are segmentation geometries with derived boxes;
- all populated legacy payloads are migrated before the workbench is exposed;
- normalized annotation rows become authoritative after migration;
- the old JSON values remain unchanged as an audit artifact; and
- legacy pages read normalized records through a v1 serializer and submit
  through the normalized annotation service.

A live database review on 2026-08-01 found eight populated grade annotation
payloads containing fourteen annotation items: thirteen `region` items and one
`polygon`. JSON `null` values are not populated annotations and must not be
migrated as annotation sets.

The migration must be idempotent and must stop activation if any populated
payload cannot be converted. The dry run and applied run report source grade,
annotation, geometry, mask-cell, normalized-instance, and tile counts. Existing
grid cells are expanded deterministically into original-image pixel tiles; a
payload without sufficient image dimensions or valid bounds is reported and
must be resolved rather than guessed.

## 17. Workbench Rollout

The new interface is user-selectable rather than project-gated.

- Existing users initially remain on the legacy interface.
- Grading entry points honor the user's saved interface preference.
- The dashboard exposes `Try new workbench` and the workbench exposes
  `Use legacy grading`.
- A global application kill switch can disable new launches without changing
  user preferences or submitted data.
- The legacy interface remains available until workflow parity and production
  use are verified.
- WebGL2 initialization failure or context loss preserves the local draft and
  presents recovery and legacy-view actions.

The preference is not exposed until migration has succeeded and all workflow
parity gates have passed.

## 18. Implementation Phases

### Phase 1: Shared grading services

- Create and claim a Bead for the feature.
- Extract eligibility, revision, task-state, consensus, linked submission,
  regrade, intra-rater, EncounterSet, and navigation rules from page routes.
- Make existing routes call the new typed services without changing behavior.

### Phase 2: Policy and normalized persistence

- Add project-policy and normalized-annotation models.
- Add reviewed, idempotent upgrade and downgrade migrations.
- Implement policy resolution, geometry validators, mask-tile processing, and
  legacy adapters.
- Rehearse and then apply the mandatory historical conversion.

### Phase 3: Administration and grading APIs

- Add the project annotation-policy API and administration workspace.
- Add workspace, submission, mask-tile, annotation-context, and preference APIs.
- Document DTOs, multipart submission, roles, scopes, CSRF, validation, and
  error behavior under `docs/API/`.

### Phase 4: React and PixiJS foundation

- Add Vite, React, TypeScript, PixiJS, frontend unit testing, and production
  manifest integration into Flask templates.
- Run the bounded vector-interaction prototype comparing direct PixiJS with a
  pinned, reduced CVAT-derived SVG layer; record benchmark results, retained
  source boundaries, removed dependencies, license notices, and the selected
  implementation before completing the production toolset.
- Implement the common state store, IndexedDB recovery, GPU camera, tiled image
  renderer, shaders, vector tools, mask worker, undo/redo, loupe, and CDR/RDR.

### Phase 5: Complete workflow parity

- Implement standard dual grading and revisions.
- Implement linked multi-disease atomic grading.
- Implement regrade adjudication and intra-rater grading.
- Implement legacy and package EncounterSet flows, including unified,
  disease-specific, image-level, and encounter-level targets.
- Verify Save & Close, Save & Next, read-only, and next-task behavior.

### Phase 6: Verification and release

- Run migration, service, API, security, frontend, browser, and performance
  gates.
- Perform side-by-side legacy/workbench submission comparisons.
- Enable the user preference only after every required gate passes.
- Update and close the Bead, export tracker state, commit documentation with the
  verified implementation, rebase, and push.

## 19. Test Plan

### 19.1 Backend and migration

- Unit-test defaults, overrides, tool intersections, multiplicity, geometry
  conversion, derived boxes, tile checksums, and every workflow command.
- Test SQL null, JSON null, all fourteen historical items, invalid metadata,
  repeat migration, downgrade behavior, and v1 round trips.
- API-test login, roles, CSRF, project/lab scope, stale context, invalid
  task/image/class/tool combinations, multipart limits, and atomic rollback.

PostgreSQL tests run inside the Compose network using the repository's required
host UID/GID and `uv run` command pattern.

### 19.2 Frontend and browser

- Unit-test DTO parsing, state transitions, undo/redo, IndexedDB versioning,
  mask tiling, shader parameters, and submission manifests.
- Browser-test mouse, pen, and touch drawing; filters; zoom/pan; loupe; CDR/RDR;
  box-to-segmentation refinement; overlapping instances; local recovery;
  context loss; read-only states; and interface switching.
- End-to-end test every workflow and confirm equivalent grades, selected
  features, comments, task state, consensus, and navigation in both interfaces.

### 19.3 Performance gates

Using representative 4K and 8K images with three visible mask layers and 200
vector objects:

- pointer-to-brush feedback is below 50 ms;
- desktop pan/zoom frame time is below 20 ms;
- reference-tablet pan/zoom frame time is below 34 ms; and
- memory remains stable when moving repeatedly between images and tasks.

## 20. Acceptance Criteria

- A project administrator can configure project tools, feature defaults and
  overrides, project classes, and project-class multiplicity.
- The same policy works across disease-specific, linked, unified EncounterSet,
  and image-level grading contexts without merging feature vocabularies.
- Every current grading workflow is available through the new workbench and
  uses the same backend rules as the legacy interface.
- Grading features always allow multiple instances; project classes enforce
  their configured multiplicity.
- Boxes can be refined into polygon or full-resolution brush segmentation with
  one authoritative geometry and a deterministic derived box.
- Disabled classes and tools cannot create new annotations, while historical
  annotations remain readable.
- All populated legacy annotations migrate successfully before rollout.
- Users can switch between workbench and legacy interfaces without changing
  grading or annotation meaning.
- Desktop mouse/keyboard and tablet pen/touch workflows pass browser tests;
  phone editing is not claimed as supported.
- Unsupported WebGL2, stale contexts, corrupt tiles, and failed submissions do
  not silently lose the local draft.
- Unsafe API requests require CSRF, and all reads/writes enforce role and
  project/lab scope.

## 21. Deferred Extensions

Project-configured image tags can later be added through explicit definitions
and assignments. They remain image-level metadata and do not alter the class,
geometry, or grading-feature resolution described here.

Advanced OpenCV.js preprocessing, server-side image pyramids, WebGPU, and
external annotation export formats are also deferred until separately approved.
