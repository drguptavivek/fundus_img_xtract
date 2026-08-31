# Encounter-Scoped WAI DR-DME Adapter Plan

## Summary

Implement the combined model with:

- Name: `madhunetra_17aug2026`
- Version: `17aug2026`
- Stable adapter/workflow key: `dr_dme`
- Provider key: `wai_dr_dme`

One encounter submission uploads all eligible macula-focused images and returns DR and DME outputs together. Automatic runs occur after supported API ingestion; manual runs are available for verified EncounterSets through the existing Wadhwani workbench.

## Architecture and persistence

- Add an encounter-scoped adapter under `remote_inference`, distinct from the existing task-scoped Glaucoma adapter. Register both by workflow key so routes dispatch without embedding provider logic.
- Create `madhunetra_17aug2026` v`17aug2026` as one `AIModel`, linked to both DR and DME through `AIModelDisease`.
- Extend `AIModelIntegration` for provider `wai_dr_dme`, storing one active database endpoint/environment pair and encrypted access token. Staging values are replaced with production values at go-live.
- Store model configuration and snapshot it into every run:
  - similarity ungradable threshold `80`
  - maximum 10 images per eye
  - upload retries after 3 and 5 seconds
  - encounter-level Submit timeout 180 seconds
  - mapping/normalization versions
- Add generic output-target configuration so future CO/cataract outputs do not require schema changes. Initial mappings:
  - DR: `No DR -> No DR`, `Mild NPDR -> Mild DR`, `Moderate NPDR -> Moderate NPDR`, `Severe NPDR -> Severe NPDR`, `PDR -> PDR`
  - DME: `No DME -> No DME`, `DME -> DME Present`
- Add:
  - `ProjectEncounterAIWorkflow` for independent automatic/manual project enablement and automatic eligibility.
  - `EncounterAIInferenceRun` for the internal UUID, encounter, model, integration, source, encounter UUID as WAI `request_id`, `report_id`, state, manifests, sanitized responses, configuration snapshot, errors, and timestamps.
  - `EncounterAIImageResult` for local image lineage, remote key, submitted/detected eye, mismatch, `is_primary`, similarity, upload attempts, quality state, and raw output.
  - `EncounterAITargetResult` for each image/target's raw label and score, mapped grade, derivation reason, and resulting `Grade`.
- Enforce one WAI DR-DME screening per encounter. Manual or recovery runs reuse its encounter UUID/request ID and report.
- Preserve the existing Glaucoma `AIInferenceRun` implementation unchanged.
- Create/reuse DR and DME image tasks before automatic inference and save `role_slot="ai"` grades for every returned image using `madhunetra_17aug2026`. Store `is_primary` separately for eye-level interpretation.
- For `similarity_score >= 80` or an image-level WAI grading error, retain raw outputs and map both local targets to `Not Gradable`.
- Make reconciliation idempotent so repeated jobs restore missing local records without duplicating tasks or grades.

## Eligibility and execution

### Automatic execution

- Trigger after a complete prospective Remidio API encounter and all image bytes are persisted.
- Do not require verification, review, thumbnails, or OCR when eligibility is `always`.
- For `if_dr_ocr_report_present`, require completed server-side OCR containing normalized `ocr.dr_report`; PDF or upstream report presence alone is insufficient.
- Re-evaluate from the OCR-completion hook.
- Expose the evaluator for future compatible custom API ingesters; creating a new custom ingestion endpoint is outside this change.

### Manual execution

- Require a verified EncounterSet, enabled project manual workflow, and current project/lab authorization.
- Use verifier-corrected EncounterSet metadata.
- Reuse and reconcile an existing WAI report rather than creating another screening.

### Image and patient eligibility

- Select images from `EncounterSetImage.metadata_json`:
  - `OD`, `R`, `right`, or `right eye` maps to `right`.
  - `OS`, `L`, `left`, or `left eye` maps to `left`.
  - Reject `OU`, missing, unknown, or ambiguous laterality.
  - Include only focus values resolving to `MACULA`.
  - Exclude `DISC` and unknown focus.
- Require at least one selected image and no more than 10 images per eye. Never truncate or split an encounter.
- Validate JPEG/PNG bytes, patient identifier length of at most 30 characters, and age from 0-120.
- Send normalized sex only when supported.
- Omit `patient.is_monocular` unless canonical patient metadata explicitly says `true`.

### Remote execution

- Persist the run/request ID before Presign.
- Presign the complete image manifest, then upload images independently.
- On transient upload failure, retry only that image after 3 seconds and then after 5 seconds.
- Refresh expired Presign URLs using the same request ID. Treat persistent signature/content-type errors as terminal.
- Call Submit only after every selected image uploads successfully. Never submit a reduced manifest.
- Store remote object keys, but never signed URLs or tokens.
- Apply the 180-second timeout to the single encounter-level Submit request, after all image uploads have completed.
- Branch on WAI error codes rather than response-detail text.
- Treat one-eye failures with a created report as partial success.
- Treat `grading_failed` as terminal in v1; a genuinely new clinical screening requires a new encounter.

## Project configuration, APIs, and workbench

- Show one `madhunetra_17aug2026 - DR + DME` workflow beside WAI Glaucoma in Project Settings, not separate DR and DME rows.
- Offer it only when:
  - the model integration and both target mappings are valid;
  - an active project profile supports EncounterSets and image-level DR plus DME tasks;
  - prospective Remidio has an active API binding for automatic execution;
  - the EncounterSet metadata contract supplies image focus and laterality.
- Automatic settings expose:
  - enabled/disabled
  - `Always run`
  - `Only when OCR-confirmed DR report is present`
  - fixed `Macula-focused images, maximum 10 per eye`
- Manual enablement remains independent from automatic enablement.
- Extend existing project workflow APIs with `workflow_key`, `execution_scope`, output targets, capability status, and blocking reasons while retaining Glaucoma compatibility.
- Make `/uploads/encountersets/wadhwani_inference?project_id=2` genuinely generic:
  - add workflow selection for Glaucoma and DR + DME;
  - use `workflow=glaucoma|dr_dme`;
  - default an omitted workflow to Glaucoma;
  - preserve Glaucoma image/task selection;
  - use encounter-level selection for DR-DME;
  - show OD/OS macula counts, eligibility issues, run state, and report ID.
- Add documented APIs:
  - `GET /api/remote-inference/encounter-set-candidates`
  - `POST /api/remote-inference/encounter-set-jobs`
- Require CSRF for mutation and preserve current role/project/lab scoping.
- Continue using `Job`/`JobItem`:
  - one DR-DME item per encounter;
  - `source_type="patient_encounter"`;
  - source ID and UUID populated;
  - task ID null;
  - maximum 25 EncounterSets per manual batch;
  - execute on the existing Wadhwani queue with a dedicated encounter-batch Celery task.
- Make recent jobs, status, and interrupted-job recovery workflow-aware.
- Update feature-scoped API documentation and the README documentation index.

## Verification and delivery

- Test migrations, provider constraints, encrypted credentials, table registration, uniqueness, upgrade, and downgrade.
- Test the client's Token authentication, Presign contract, exact upload content type, absence of token on storage PUT, 3/5-second retries, Presign refresh, upload barrier, 180-second encounter Submit timeout, error parsing, and secret sanitization.
- Test automatic pre-verification execution, manual verified-only execution, strict OCR-confirmed DR-report eligibility, macula filtering, laterality mapping, single-eye omission of `is_monocular`, patient validation, and 10-per-eye limits.
- Test request/report reuse, per-image persistence, primary flags, laterality mismatches, raw score retention, threshold-derived Not Gradable, mappings, immediate tasks/grades, reconciliation, partial success, and duplicate prevention.
- Test Project Settings capability blockers, independent automatic/manual controls, generic workflow selection, backward-compatible URLs, authorization, CSRF, one `JobItem` per encounter, status, recent jobs, and resume behavior.
- Run existing WAI Glaucoma, EncounterSet task-routing/verification, Remidio ingestion/OCR, project configuration, and mobile/direct inference suites as regressions. Run PostgreSQL tests serially inside Compose with host UID/GID.
- Create and manage a Beads feature, export `.beads/issues.jsonl`, stage only owned files, verify the staged diff, commit once after verification, pull/rebase, push, and confirm the branch is current.
- After staging credentials are supplied, run one supervised staging screening and verify the request ID, report ID, image results, mapped grades, job state, and absence of secrets in logs before replacing the stored endpoint/token with production values.
