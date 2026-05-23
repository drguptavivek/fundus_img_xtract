# Remidio EncounterSet Metadata Contract

This document records the current Remidio API sample evidence and how those
payloads map into EncounterSet metadata fields.

## Sample Evidence

Discovery outputs are stored under `REMIDIO_Samples/` and are gitignored
because they can contain patient identifiers, clinical sample payload structure,
and source identifiers. The single-exam JSON helper writes sanitized payloads.
The date-range CSV helper preserves source patient fields, medical history, and
report comments for local schema analysis; it still redacts signed URLs because
those are credentials rather than metadata. CSV outputs must not be committed.

Current CSV exports:

- `REMIDIO_Samples/date_range_rpc_comoph_2_20042026_29042026/`
  - `exam_count`: 11
  - `image_rows`: 86
  - `report_rows`: 13
- `REMIDIO_Samples/date_range_rpc_comoph_2_01032026_31032026/`
  - `exam_count`: 89
  - `image_rows`: 513
  - `report_rows`: 164

Current single-exam samples include:

- PRISTINE active and graded exams.
- FOP active exams with `aiReport`, `gmaReport`, and `mediosAIReport`.
- PRISTINE doctor reports with PDF paths and linked image IDs.

Endpoint behavior:

- `getPatientWithLastExam/{siteIdentifier}/{mrn}` uses numeric Remidio
  `siteId`.
- `getExamsByDate/{startDate}/{endDate}/{siteCustomIdentifier}` uses the
  Remidio dashboard custom identifier, for example `rpc_comoph_2`.

## Metadata Scope Strategy

Remidio data is split into three classes.

1. Source-only hidden metadata:
   - Remidio IDs.
   - Remidio local IDs.
   - signed URL presence/source fields.
   - raw source JSON.
   - source user/provider IDs.

2. Verification metadata:
   - MRN, DOB/age, sex.
   - capture date/time.
   - device type.
   - laterality.
   - fundus field.
   - image quality.
   - montage status.
   - report diagnosis and refer flags.

3. Derived operational metadata:
   - clinical image count.
   - report document count.
   - report presence flags.
   - AI/GMA report presence.

Graders should not see PII, signed URLs, raw source payloads, source
user/provider identity fields, or diagnosis fields that would unblind the
grading task.

Clinical structured values and PII are intentionally separate concepts here.
Structured report diagnoses such as `left_eye_diagnosis` and
`right_eye_diagnosis` are clinical metadata, not PII. They may still be hidden
from graders for blinding, but that is controlled by `visible_to_grader`, not
by the PII flag.

## Seeded Field Masters

The migration `e0f1a2b3c4d5_seed_remidio_metadata_and_encounter_set.py` seeds
Remidio-specific field masters and a standard inactive EncounterSetType:

- code: `remidio_api_standard`
- name: `Remidio API Standard Encounter Set`

It also reuses existing generic field masters where appropriate:

- `hospital_UHID`
- `patient_name`
- `patient_dob`
- `patient_age_yrs`
- `sex`
- `laterality`

The standard EncounterSetType is inactive initially because image and encounter
grading schemes must be selected by an admin before use.

The `json` metadata field type is now a first-class upload metadata field type.
It is used for source catch-all payloads and list-like source values such as
linked image IDs, diagnosis arrays, edit operation arrays, and original image
ID arrays.

## PII And Redaction Policy

Raw Remidio catch-all metadata is treated as PII by default at every scope:

- `remidio_patient_raw_metadata`
- `remidio_encounter_raw_metadata`
- `remidio_image_exif_metadata`
- `remidio_image_raw_metadata`
- `remidio_report_raw_metadata`

The mapper keeps raw JSON blobs full-fidelity for controlled DB storage. It does
not redact patient identifiers, source user/provider identifiers, clinical text,
or signed/source URL values before persistence. These fields are marked PII so
access control, verification UI, exports, and future task creation can decide
what to reveal without losing the original source payload.

Medical history, doctor comments, report PDFs, document images, report
documents, raw source JSON, and source user/provider identifiers should be
handled as PII even when the source report type is not a clinical image. These
fields must not be visible to graders unless a future workflow explicitly makes
a de-identified derivative.

## Patient Fields

| Key | Source | Type | PII | Verification |
|---|---|---:|---:|---:|
| `hospital_UHID` | `patientDetails.mrn` | text | yes | yes |
| `remidio_patient_id` | `patientDetails.id` | text | no | no |
| `patient_name` | `firstName` + `lastName` | text | yes | yes |
| `patient_dob` | `patientDetails.dateOfBirth` | date | yes | yes |
| `patient_age_yrs` | derived | integer | yes | yes |
| `sex` | `patientDetails.gender` | select | yes | yes |
| `remidio_site_id` | `patientDetails.siteId` | text | no | no |
| `remidio_site_custom_identifier` | routing config | text | no | no |
| `remidio_patient_raw_metadata` | `patientDetails` | json | yes | no |

## Encounter Fields

| Key | Source | Type | Verification |
|---|---|---:|---:|
| `remidio_exam_id` | `examDetails.id` | text | no |
| `remidio_exam_local_id` | `examDetails.localId` | text | no |
| `exam_code` | `examDetails.examCustomId` | text | yes |
| `capture_datetime` | `examDetails.examDate` | datetime | yes |
| `remidio_exam_report_datetime` | `examDetails.reportDate` | datetime | yes |
| `device_type` | `examDetails.deviceType[]` | select | yes |
| `exam_state` | `examDetails.examState` | select | no |
| `medical_history` | `examDetails.medicalHistory` | textarea | yes |
| `has_doctor_report` | derived from `report` | boolean | no |
| `has_ai_report` | derived from `aiReport` | boolean | no |
| `has_gma_report` | derived from `gmaReport` | boolean | no |
| `has_medios_ai_report` | derived from `mediosAIReport` | boolean | no |
| `clinical_image_count` | derived | integer | no |
| `report_document_count` | derived | integer | no |
| `remidio_encounter_raw_metadata` | source encounter object | json | no |

## Image Fields

| Key | Source | Type | Verification |
|---|---|---:|---:|
| `remidio_image_id` | image `id` | text | no |
| `remidio_image_local_id` | image `localId` | text | no |
| `remidio_image_exam_id` | image `examId` | text | no |
| `image_bucket` | source bucket name | select | no |
| `image_variant` | `STANDARD` / `EDITED` | select | yes |
| `image_capture_datetime` | image `date` | datetime | yes |
| `image_device_type` | image `deviceType` | select | yes |
| `laterality` | image `laterality` | select | yes |
| `fundus_field` | image `field` | select | yes |
| `image_segment` | image `imageSegment` | select | yes |
| `remidio_image_quality` | image `quality` | select | yes |
| `is_cropped` | image `isCropped` | boolean | yes |
| `is_montage` | derived from `editOperations` | boolean | yes |
| `edit_operations` | image `editOperations[]` | json | yes |
| `original_remidio_image_ids` | image `originalImageIds[]` | json | no |
| `width_px` | image `width` | integer | no |
| `height_px` | image `height` | integer | no |
| `source_path_present` | image `path` | boolean | no |
| `thumbnail_path_present` | image `thumbnailPath` | boolean | no |
| `disc_present` | `discQualityResults.discPresent` | boolean | no |
| `disc_quality_acceptable` | `discQualityResults.acceptableQuality` | boolean | no |
| `disc_quality_score` | `discQualityResults.qualityScore` | decimal | no |
| `disc_roi_x` | `discQualityResults.roiX` | decimal | no |
| `disc_roi_y` | `discQualityResults.roiY` | decimal | no |
| `remidio_image_exif_metadata` | image `metadata` | json | no |
| `remidio_image_raw_metadata` | full image object | json | no |

`disc_roi_x` and `disc_roi_y` are single decimal values in the observed raw
payloads, not lists.

## Report / Document Fields

| Key | Source | Type | Verification |
|---|---|---:|---:|
| `remidio_report_id` | report `id` | text | no |
| `remidio_report_type` | normalized object name | select | no |
| `remidio_report_exam_id` | report `examId` | text | no |
| `remidio_report_patient_id` | report `patientId` | text | no |
| `remidio_report_local_id` | report `localId` | text | no |
| `remidio_report_datetime` | `reportDate` / `generatedDate` | datetime | yes |
| `report_path_present` | report `path` | boolean | no |
| `linked_remidio_image_ids` | report `imageIds[]` | json | no |
| `refer_required` | doctor report | boolean | yes |
| `left_eye_diagnosis` | doctor report | json | yes |
| `left_eye_report_comments` | doctor report | textarea | yes |
| `right_eye_diagnosis` | doctor report | json | yes |
| `right_eye_report_comments` | doctor report | textarea | yes |
| `reporting_doctor_id` | doctor report | text | no |
| `ai_confidence` | AI report | decimal | no |
| `ai_input_sufficient` | AI report | boolean | no |
| `ai_quality_sufficient` | AI report | boolean | no |
| `ai_suggested_refer` | AI report | boolean | no |
| `number_of_heatmap_images` | AI report | integer | no |
| `gma_left_eye_cdr` | GMA report | decimal | no |
| `gma_right_eye_cdr` | GMA report | decimal | no |
| `gma_suggested_refer` | GMA report | boolean | no |
| `gma_patient_level_result` | Medios AI report | text | no |
| `remidio_report_raw_metadata` | full report object | json | no |

The verification column above describes whether the field should normally be
reviewed during verification. It is separate from the PII flag. Raw metadata
fields remain PII even when they are not normally edited or reviewed.

Remidio's doctor report object arrives under the source key `report`; the mapper
stores its normalized `remidio_report_type` as `doctor_report` so it fits the
same select field as `aiReport`, `gmaReport`, and `mediosAIReport`.

## Mapper Service

`remidio_api_integration.mapper` converts one Remidio exam payload into:

- patient metadata dict
- encounter metadata dict
- image metadata dict list
- report metadata dict list

The mapper is persistence-free. It emits explicit normalized metadata fields and
also preserves raw JSON catch-all metadata without redaction for controlled DB
storage. Signed/source URL values may therefore exist inside raw metadata; task
creation, UI, export, and API layers must treat raw metadata fields as
PII-restricted and must avoid exposing them to graders by default.

## Next Service Boundary

The next service should be a duplicate-safe Remidio EncounterSet save/upsert
service.

Proposed idempotency keys:

- patient: `connection_id + remidio_patient_id`
- encounter: `connection_id + remidio_exam_id`
- image: `connection_id + remidio_exam_id + remidio_image_id`
- report: `connection_id + remidio_exam_id + report_type + remidio_report_id`

This save service should create or update local EncounterSet rows without
creating duplicate patients, encounters, images, documents, reports, or grading
tasks.
