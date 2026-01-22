# Dataset Creation & Screening

## Overview
Dataset creation is a two‑phase process:
1) **Create a curated dataset** by selecting tasks based on filters.
2) **Screen images** to include/exclude each task before export.

This doc focuses on the dataset curation screen and the screening workflow.

## Roles & Access
- Requires dataset‑related roles (e.g., `dataset_creator`, `data_manager`, `analytics_viewer`).
- All access is scoped by lab units/hospitals via RBAC + ABAC.

## Create a Dataset
1. Go to **Analytics → Dataset Curation**.
2. Choose disease and filters (date ranges, grading status, AI model, etc.).
3. Create the dataset with a name + purpose.
4. System builds a list of candidate tasks for screening.

## Screening Page
The screening page shows:
- **List View** (left): scrollable list of tasks/images.
- **Viewer** (right): shows selected image + controls.
- **Gallery View**: optional grid of thumbnails for quick navigation.

### Controls
- **Include/Exclude**: toggle whether a task is included in export.
- **Add More**: add additional tasks based on filters.
- **Sort**: Task ID or Date Added.
- **Filter**: All / Included / Excluded.
- **Refresh PII status**: refresh stored OCR PII status from DB (no re‑detect).

### Keyboard Navigation (List View)
- **Arrow Down**: next visible row.
- **Arrow Up**: previous visible row.

## PII Screening (OCR)
Each image has a PII badge:
- **Pending** = no OCR record exists yet.
- **No PII / PII detected** = stored DB status.

Behavior:
- Clicking an image triggers OCR if status is pending.
- “Refresh PII status” pulls stored results (no OCR run).
- “Redetect” forces OCR and updates stored results.

## Gallery View
- Thumbnails load lazily to reduce load.
- Clicking a thumbnail opens the viewer and loads the image + PII status.

## Dataset Status
- **Active**: still editable.
- **Finalized**: locked for changes; ready for export.

## Export
Once screening is complete:
- Click **Export** to generate dataset output.
- Included items are exported; excluded items are skipped.

## Troubleshooting
- If PII badges remain **Pending**, OCR hasn’t been run or stored for those images.
- Use **Refresh PII status** to load DB status without running OCR.
- Use **Redetect** only when you need to rerun OCR.
